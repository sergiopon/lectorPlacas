"""Métricas, criterio de aceptación y CLI de la evaluación del OCR (spec 039).

Aplica el criterio M-04 de ADR-014 y escribe reportes sin textos de placa.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import math
import os
import random
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Final, cast

import cv2
import numpy as np
import numpy.typing as npt

from ocr_training.common import (
    DATASETS_DIR, PROJECT_ROOT, RUNS_DIR, TRAINING_DIR, TrainingError, check_ocr_onnx,
    require_asset, sha256_file, validate_annotations,
)
from ocr_training.mix_split import CATEGORIES, category

BASELINE_MODEL_ID: Final[str] = "fpo-cct-xs-v2-global"
BASELINE_ONNX: Final[Path] = PROJECT_ROOT / "models" / BASELINE_MODEL_ID / "cct_xs_v2_global.onnx"
BASELINE_SHA256: Final[str] = "8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44"
REPORTS_DIR: Final[Path] = RUNS_DIR / "reports"
MAX_CER: Final[float] = 0.03
MAX_CER_UPPER: Final[float] = 0.05
MIN_TEST_SAMPLES: Final[int] = 100
BOOTSTRAP_ROUNDS: Final[int] = 2000
EVAL_BATCH_SIZE: Final[int] = 64

Predictor = Callable[[Sequence[npt.NDArray[np.uint8]]], list[str]]
PredictorFactory = Callable[[Path, Path], Predictor]

_PREDICTION_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{0,10}$")
_FILE_MODE: Final[int] = 0o600


@dataclass(frozen=True, slots=True)
class ModelMetrics:
    """Métricas del split: `cer_by_category` vale `None` sin muestras de la categoría."""

    samples: int
    cer: float
    exact_match_rate: float
    cer_ci95: tuple[float, float]
    cer_by_category: dict[str, float | None]
    samples_by_category: dict[str, int]


def levenshtein(a: str, b: str) -> int:
    """Calcula la distancia de edición entre dos cadenas."""
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def normalize_prediction(text: str) -> str:
    """Normaliza un texto predicho igual que el adaptador de runtime (spec 017)."""
    if "_" in text or _PREDICTION_REGEX.fullmatch(text) is None:
        return ""
    return text


def read_split(csv_path: Path) -> list[tuple[Path, str, str]]:
    """Lee el split `test` con sus grupos; devuelve `(imagen, texto real, grupo)`."""
    split_dir = csv_path.parent
    if split_dir.name != "test":
        raise TrainingError("la aceptación se mide en el split test")
    validate_annotations(csv_path)
    groups_path = split_dir / "groups.csv"
    if not groups_path.is_file():
        raise TrainingError("falta groups.csv")
    with groups_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ("image_path", "group_id"):
            raise TrainingError("columnas inválidas en groups.csv")
        group_of = {row["image_path"]: row["group_id"] for row in reader}
    rows: list[tuple[Path, str, str]] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            image_path = row["image_path"]
            if PurePosixPath(image_path).name.startswith("syn_"):
                raise TrainingError("el split de evaluación contiene sintéticos")
            if image_path not in group_of:
                raise TrainingError(f"grupo ausente para {image_path}")
            rows.append(((split_dir / image_path).resolve(), row["plate_text"], group_of[image_path]))
    return rows


def _bootstrap_ci(
    distances: Sequence[int], truths: Sequence[str], groups: Sequence[str], seed: int, rounds: int
) -> tuple[float, float]:
    """Estima el IC 95 % del CER remuestreando grupos completos."""
    order: list[str] = []
    totals: dict[str, list[int]] = {}
    for index, group in enumerate(groups):
        if group not in totals:
            totals[group] = [0, 0]
            order.append(group)
        totals[group][0] += distances[index]
        totals[group][1] += len(truths[index])
    pool = [totals[group] for group in order]
    rng = random.Random(seed)
    sample_cers: list[float] = []
    for _ in range(rounds):
        total_distance = total_length = 0
        for _ in range(len(pool)):
            distance, length = rng.choice(pool)
            total_distance += distance
            total_length += length
        sample_cers.append(total_distance / total_length)
    sample_cers.sort()
    return sample_cers[math.floor(0.025 * rounds)], sample_cers[math.ceil(0.975 * rounds) - 1]


def compute_metrics(
    predictions: Sequence[str], truths: Sequence[str], groups: Sequence[str], seed: int,
    rounds: int = BOOTSTRAP_ROUNDS,
) -> ModelMetrics:
    """Calcula las métricas de un modelo sobre el split de evaluación."""
    if not predictions or len(predictions) != len(truths) or len(predictions) != len(groups):
        raise TrainingError("predicciones, verdades y grupos no coinciden")
    distances = [levenshtein(p, t) for p, t in zip(predictions, truths, strict=True)]
    exact = sum(1 for p, t in zip(predictions, truths, strict=True) if p == t)
    cer_by_category: dict[str, float | None] = {}
    samples_by_category: dict[str, int] = {}
    for name in CATEGORIES:
        picked = [index for index, truth in enumerate(truths) if category(truth) == name]
        samples_by_category[name] = len(picked)
        cer_by_category[name] = (
            sum(distances[index] for index in picked)
            / sum(len(truths[index]) for index in picked)
            if picked
            else None
        )
    return ModelMetrics(
        samples=len(predictions),
        cer=sum(distances) / sum(len(truth) for truth in truths),
        exact_match_rate=exact / len(predictions),
        cer_ci95=_bootstrap_ci(distances, truths, groups, seed, rounds),
        cer_by_category=cer_by_category,
        samples_by_category=samples_by_category,
    )


def decide(candidate: ModelMetrics, baseline: ModelMetrics) -> list[str]:
    """Aplica el criterio de aceptación; devuelve los motivos de rechazo."""
    reasons: list[str] = []
    if candidate.samples < MIN_TEST_SAMPLES:
        reasons.append(f"muestra insuficiente: {candidate.samples} < {MIN_TEST_SAMPLES}")
    if candidate.cer > MAX_CER:
        reasons.append(f"CER {candidate.cer:.4f} > {MAX_CER}")
    if candidate.cer_ci95[1] > MAX_CER_UPPER:
        reasons.append(f"cota superior del IC 95 % {candidate.cer_ci95[1]:.4f} > {MAX_CER_UPPER}")
    if candidate.cer >= baseline.cer:
        reasons.append("no mejora el CER del modelo base")
    if candidate.exact_match_rate < baseline.exact_match_rate:
        reasons.append("empeora la coincidencia exacta del modelo base")
    return reasons


def onnx_predictor(model_path: Path, plate_config: Path) -> Predictor:
    """Construye un predictor ONNX en CPU para un modelo y su configuración."""
    from fast_plate_ocr import LicensePlateRecognizer

    recognizer = LicensePlateRecognizer(
        onnx_model_path=model_path,
        plate_config_path=plate_config,
        providers=["CPUExecutionProvider"],
    )
    return lambda images: [prediction.plate for prediction in recognizer.run(list(images))]


def _predict_metrics(
    predictor: Predictor, images: Sequence[npt.NDArray[np.uint8]], truths: Sequence[str],
    groups: Sequence[str], seed: int,
) -> ModelMetrics:
    """Ejecuta el predictor por lotes y calcula sus métricas."""
    predictions: list[str] = []
    for start in range(0, len(images), EVAL_BATCH_SIZE):
        batch = list(images[start : start + EVAL_BATCH_SIZE])
        texts = predictor(batch)
        if len(texts) != len(batch):
            raise TrainingError("el predictor devolvió un número de textos distinto")
        predictions.extend(normalize_prediction(text) for text in texts)
    return compute_metrics(predictions, truths, groups, seed)


def evaluate(
    crops_csv: Path, candidate_onnx: Path, baseline_onnx: Path, plate_config: Path, seed: int,
    predictor_factory: PredictorFactory = onnx_predictor,
) -> dict[str, object]:
    """Evalúa el candidato frente al base sobre el split `test` y decide la aceptación."""
    rows = read_split(crops_csv)
    images: list[npt.NDArray[np.uint8]] = []
    truths: list[str] = []
    groups: list[str] = []
    for path, text, group in rows:
        image = cv2.imread(str(path))
        if image is None:
            raise TrainingError(f"no se pudo leer el recorte: {path.name}")
        images.append(cast("npt.NDArray[np.uint8]", cv2.cvtColor(image, cv2.COLOR_BGR2RGB)))
        truths.append(text)
        groups.append(group)
    candidate, baseline = [
        _predict_metrics(predictor_factory(model, plate_config), images, truths, groups, seed)
        for model in (candidate_onnx, baseline_onnx)
    ]
    reasons = decide(candidate, baseline)
    candidate_moto, baseline_moto = candidate.cer_by_category["moto"], baseline.cer_by_category["moto"]
    moto_samples = candidate.samples_by_category["moto"]
    regressed = candidate_moto is not None and baseline_moto is not None and candidate_moto > baseline_moto
    warnings = [f"regresión en motos (muestra pequeña: {moto_samples} recortes)"] if regressed else []
    return {
        "version": 1, "samples": len(rows), "accepted": not reasons, "reasons": reasons,
        "warnings": warnings, "candidate": dataclasses.asdict(candidate),
        "baseline": dataclasses.asdict(baseline),
    }


def write_report(report: Mapping[str, object], reports_dir: Path, now: datetime) -> Path:
    """Escribe el reporte JSON con nombre UTC; falla si no hay zona horaria o ya existe."""
    if now.tzinfo is None:
        raise TrainingError("se requiere una fecha con zona horaria")
    reports_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = reports_dir / f"ocr-eval-{now.astimezone(UTC):%Y%m%dT%H%M%SZ}.json"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
    except FileExistsError as exc:
        raise TrainingError("el reporte ya existe") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(report, indent=2, sort_keys=True))
    return path


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de la CLI de evaluación."""
    parser = argparse.ArgumentParser(description="Evalúa la aceptación del OCR mezclado.")
    parser.add_argument("--crops", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Evalúa el candidato desde la CLI; devuelve 0 si se acepta y 1 si se rechaza."""
    args = build_parser().parse_args(argv)
    crops = (DATASETS_DIR / args.crops).resolve()
    if DATASETS_DIR.resolve() not in crops.parents:
        raise TrainingError(f"crops fuera de DATASETS_DIR: {args.crops}")
    candidate_path = (TRAINING_DIR / args.candidate).resolve()
    if not candidate_path.is_file():
        raise TrainingError(f"candidato inexistente: {args.candidate}")
    check_ocr_onnx(candidate_path)
    plate_config = require_asset("cct_xs_v2_global_plate_config.yaml")
    if not BASELINE_ONNX.is_file() or sha256_file(BASELINE_ONNX) != BASELINE_SHA256:
        raise TrainingError("modelo base no verificado: ejecute lector models fetch en la raíz")
    report = evaluate(crops, candidate_path, BASELINE_ONNX, plate_config, args.seed)
    report["candidate_sha256"] = sha256_file(candidate_path)
    report["baseline_model_id"] = BASELINE_MODEL_ID
    report_path = write_report(report, REPORTS_DIR, datetime.now(UTC))
    candidate = cast("dict[str, object]", report["candidate"])
    baseline = cast("dict[str, object]", report["baseline"])
    ci_low, ci_high = cast("tuple[float, float]", candidate["cer_ci95"])
    print(
        f"candidato: muestras={candidate['samples']} cer={cast(float, candidate['cer']):.4f} "
        f"ic95=[{ci_low:.4f}, {ci_high:.4f}] exacta={cast(float, candidate['exact_match_rate']):.4f}"
    )
    print(f"base: cer={cast(float, baseline['cer']):.4f} "
          f"exacta={cast(float, baseline['exact_match_rate']):.4f}")
    print(f"decision={'ACEPTAR' if report['accepted'] else 'RECHAZAR'}")
    for reason in cast("list[str]", report["reasons"]):
        print(f"motivo: {reason}")
    for warning in cast("list[str]", report["warnings"]):
        print(f"aviso: {warning}")
    print(f"reporte={report_path.name}")
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
