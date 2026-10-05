"""Tests de aceptación adicionales.

Cubren casos borde que la spec no enumera explícitamente: qué estados entran en el
emparejamiento, la frontera exacta de la tolerancia temporal, el uso único de cada
placa del ground truth, los denominadores nulos del CER y las guardias de ruta y de
placas de los reportes y del CSV de OCR.
"""

from __future__ import annotations

import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lector_placas.domain.entities import ReviewStatus, SightingRecord, VehicleType
from lector_placas.domain.errors import EvaluationError, UnsafePathError
from lector_placas.evaluation.cer import character_error_rate, exact_match_rate, levenshtein
from lector_placas.evaluation.ground_truth import GroundTruth, GroundTruthPlate, load_ground_truth
from lector_placas.evaluation.metrics import compute_metrics, overlaps
from lector_placas.evaluation.ocr_dataset import read_ocr_annotations
from lector_placas.evaluation.report import write_report

T0 = datetime(2026, 9, 24, tzinfo=UTC)
CONFIRMED = ReviewStatus.CONFIRMED
UNVERIFIED = ReviewStatus.UNVERIFIED
REJECTED = ReviewStatus.REJECTED


def rec(
    sid: int, text: str, first: int, last: int, status: ReviewStatus = CONFIRMED
) -> SightingRecord:
    return SightingRecord(
        sid,
        1,
        sid,
        first,
        last,
        VehicleType.CAR,
        text,
        text,
        0.9,
        0.9,
        3,
        status,
        (),
        (),
        None,
        T0,
        None,
    )


def truth_with(*plates: GroundTruthPlate) -> GroundTruth:
    return GroundTruth(
        version=1, video_sha256="a" * 64, subset="street_day", camera="fixed", plates=plates
    )


def plate(text: str, first: int, last: int) -> GroundTruthPlate:
    return GroundTruthPlate(
        text=text,
        vehicle_type=VehicleType.CAR,
        first_seen_ms=first,
        last_seen_ms=last,
        legible=True,
    )


def test_rejected_sightings_never_match() -> None:
    """Un avistamiento rechazado no cuenta ni para recall_any (ANY_STATUS lo excluye)."""
    truth = truth_with(plate("ABC123", 1000, 2000))
    records = [rec(1, "ABC123", 1000, 2000, REJECTED), rec(2, "ABC123", 1200, 1800, UNVERIFIED)]
    metrics = compute_metrics(records, truth)
    assert (metrics.any_matched, metrics.confirmed_matched, metrics.confirmed_total) == (1, 0, 0)
    assert metrics.recall_any == 1.0


def test_tolerance_boundary_is_inclusive() -> None:
    """La tolerancia se aplica con <=: justo en el borde solapa, un ms más allá no."""
    target = plate("ABC123", 5000, 6000)
    assert overlaps(rec(1, "ABC123", 2000, 3999), target, 1000) is False
    assert overlaps(rec(1, "ABC123", 2000, 4000), target, 1000) is True
    assert overlaps(rec(1, "ABC123", 7000, 8000), target, 1000) is True
    assert overlaps(rec(1, "ABC123", 7001, 8000), target, 1000) is False


def test_a_matched_plate_is_not_reused() -> None:
    """Cada placa legible del ground truth se empareja como máximo una vez."""
    truth = truth_with(plate("ABC123", 1000, 2000))
    records = [
        rec(1, "ABC123", 1000, 2000, CONFIRMED),
        rec(2, "ABC123", 1000, 2000, UNVERIFIED),
    ]
    metrics = compute_metrics(records, truth)
    assert (metrics.confirmed_matched, metrics.any_matched) == (1, 1)


def test_confirmed_without_ground_truth_lowers_precision() -> None:
    """Una confirmada que no existe en el ground truth no es recuerdo: solo baja la precisión."""
    truth = truth_with(plate("ABC123", 1000, 2000))
    records = [rec(1, "XYZ98K", 1000, 2000, CONFIRMED)]
    metrics = compute_metrics(records, truth)
    assert metrics.confirmed_matched == 0
    assert metrics.precision_confirmed == 0.0
    assert metrics.recall_confirmed == 0.0


def test_non_legible_plates_do_not_count() -> None:
    """Las placas marcadas como no legibles quedan fuera del denominador del recall."""
    truth = truth_with(
        plate("ABC123", 1000, 2000),
        GroundTruthPlate(
            text="",
            vehicle_type=VehicleType.TRUCK,
            first_seen_ms=3000,
            last_seen_ms=4000,
            legible=False,
        ),
    )
    metrics = compute_metrics([], truth)
    assert metrics.gt_legible == 1


def test_cer_denominator_uses_the_truth_length() -> None:
    """El CER divide entre la longitud de la verdad, no de la predicción."""
    assert character_error_rate([("", "ABCD")]) == pytest.approx(1.0)
    assert character_error_rate([("ABCDE", "ABCD")]) == pytest.approx(1 / 4)
    with pytest.raises(EvaluationError):
        character_error_rate([("ABCD", "")])


def test_levenshtein_has_no_transposition_shortcut() -> None:
    """La distancia es la clásica: una transposición cuesta 2, no 1."""
    assert levenshtein("AB", "BA") == 2
    assert levenshtein("", "ABC") == 3
    assert levenshtein("ABC", "") == 3
    assert exact_match_rate([("ABC", "ABC"), ("ABC", "ABD")]) == pytest.approx(0.5)


def test_report_rejects_a_plate_hidden_in_a_nested_value(tmp_path: Path) -> None:
    """La guardia de placas mira el JSON serializado completo, no solo las claves de primer nivel."""
    payload = {"kind": "video", "detalle": {"muestras": ["ABC123"]}}
    with pytest.raises(EvaluationError):
        write_report(tmp_path / "reports", payload, T0)
    assert not (tmp_path / "reports").exists() or not list((tmp_path / "reports").iterdir())


def test_report_without_plates_is_private_and_readable(tmp_path: Path) -> None:
    """Un reporte sin placas se escribe con permisos 0600 y contenido íntegro."""
    path = write_report(tmp_path / "reports", {"kind": "ocr", "samples": 12, "cer": 0.0}, T0)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "kind": "ocr",
        "samples": 12,
        "cer": 0.0,
    }


def test_ocr_annotations_reject_an_absolute_image_path(tmp_path: Path) -> None:
    """Una ruta absoluta de imagen queda fuera del directorio del CSV (SEG-12)."""
    csv_path = tmp_path / "annotations.csv"
    csv_path.write_text("image_path,plate_text\n/etc/passwd,ABC123\n", encoding="utf-8")
    with pytest.raises(UnsafePathError):
        read_ocr_annotations(csv_path)


def test_ocr_annotations_allow_extra_columns(tmp_path: Path) -> None:
    """Solo se exigen las dos columnas obligatorias; las extra se ignoran."""
    csv_path = tmp_path / "annotations.csv"
    csv_path.write_text("image_path,plate_text,nota\nimages/a.png,ABC123,ok\n", encoding="utf-8")
    assert read_ocr_annotations(csv_path) == [((tmp_path / "images" / "a.png").resolve(), "ABC123")]


def test_ground_truth_rejects_unknown_fields(tmp_path: Path) -> None:
    """El esquema del ground truth es cerrado: un campo desconocido es un error."""
    csv_path = tmp_path / "gt.json"
    csv_path.write_text(
        json.dumps(
            {
                "version": 1,
                "video_sha256": "a" * 64,
                "subset": "street_day",
                "camera": "fixed",
                "plates": [
                    {
                        "text": "ABC123",
                        "vehicle_type": "car",
                        "first_seen_ms": 1,
                        "last_seen_ms": 2,
                        "legible": True,
                        "confianza": 0.9,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EvaluationError):
        load_ground_truth(csv_path)
