"""Modo demo de lector-web: datos sintéticos en una carpeta temporal."""

from __future__ import annotations

import hashlib
import random
import secrets
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import cv2
import numpy as np

from lector_placas.application.ports import (
    CropStore,
    ImageBGR,
    KeyProvider,
    PlateRepository,
    ProgressReporter,
    ProgressUpdate,
    RunStart,
    RunStats,
    VideoInfo,
)
from lector_placas.cli import composition
from lector_placas.domain.entities import (
    ConsolidatedPlate,
    CropQuality,
    ReviewStatus,
    Sighting,
    UnverifiedReason,
    VehicleType,
)
from lector_placas.domain.errors import ProcessingCancelledError
from lector_placas.infrastructure.config import AppConfig
from lector_placas.infrastructure.input_validation import sha256_file
from lector_placas.web.jobs import JobRunner

DEMO_SEED: Final[int] = 2026


def demo_start(now: datetime) -> datetime:
    """Devuelve el instante base de la demo: `now` truncado a la hora, menos 2 días."""
    return now.astimezone(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=2)


DEMO_PROFILES: Final[tuple[str, ...]] = (
    "parqueadero",
    "calle_lenta",
    "calle_rapida",
    "patrulla",
    "calle_lenta",
)
DEMO_VIDEOS: Final[tuple[str, ...]] = ("demo_entrada.mp4", "demo_calle.mp4", "demo_patrulla.mp4")
LETTERS: Final[str] = "ABCDEFGHJKLMNPRSTUVWXYZ"
DIGITS: Final[str] = "0123456789"
PLATE_SIZE: Final[tuple[int, int]] = (300, 100)
PLATE_BGR: Final[tuple[int, int, int]] = (0, 204, 255)
_K_CORRECTED: Final[int] = 5
_K_REJECTED: Final[int] = 6
_K_ILLEGIBLE: Final[int] = 7
_MOTORCYCLE_REMAINDER: Final[int] = 4
_DEMO_RUNS: Final[int] = 5


class DemoKeyProvider:
    """Proveedor de clave maestra aleatoria que vive solo en memoria."""

    def __init__(self) -> None:
        """Genera la clave de 32 bytes."""
        self._key = secrets.token_bytes(32)

    def master_key(self) -> bytes:
        """Devuelve la clave de demo."""
        return self._key


def render_plate(text: str) -> ImageBGR:
    """Dibuja una placa sintética con el texto dado.

    Args:
        text: texto inventado de la placa.

    Returns:
        Imagen BGR de 100x300 píxeles.
    """
    imagen: ImageBGR = np.full((100, 300, 3), PLATE_BGR, np.uint8)
    cv2.rectangle(imagen, (2, 2), (297, 97), (0, 0, 0), 4)
    rotulo = f"{text[:3]} {text[3:]}"
    (w, h), _ = cv2.getTextSize(rotulo, cv2.FONT_HERSHEY_SIMPLEX, 1.6, 4)
    cv2.putText(
        imagen,
        rotulo,
        ((300 - w) // 2, (100 + h) // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.6,
        (0, 0, 0),
        4,
        cv2.LINE_AA,
    )
    return imagen


def plate_text(rng: random.Random, vehicle_type: VehicleType) -> str:
    """Genera un texto de placa inventado.

    Args:
        rng: generador pseudoaleatorio.
        vehicle_type: tipo de vehículo.

    Returns:
        Tres letras y tres dígitos; para motos, tres letras, dos dígitos y una letra.
    """
    letters = "".join(rng.choice(LETTERS) for _ in range(3))
    if vehicle_type is VehicleType.MOTORCYCLE:
        digits = "".join(rng.choice(DIGITS) for _ in range(2))
        return letters + digits + rng.choice(LETTERS)
    digits = "".join(rng.choice(DIGITS) for _ in range(3))
    return letters + digits


def create_demo_root() -> Path:
    """Crea la carpeta temporal de demo con tres videos de relleno.

    Returns:
        Ruta de la carpeta temporal.
    """
    root = Path(tempfile.mkdtemp(prefix="lector-demo-"))
    root.chmod(0o700)
    videos = root / "videos"
    videos.mkdir()
    videos.chmod(0o700)
    for name in DEMO_VIDEOS:
        video = videos / name
        video.write_bytes(b"lectorPlacas demo\n")
        video.chmod(0o600)
    return root


def demo_config(config: AppConfig, root: Path) -> AppConfig:
    """Devuelve la configuración con la raíz apuntando a la carpeta de demo.

    Args:
        config: configuración original.
        root: carpeta temporal de demo.

    Returns:
        Copia de la configuración con `root_dir` sustituido.
    """
    return config.model_copy(update={"root_dir": root})


def _shifted(text: str) -> str:
    """Sustituye el primer carácter por el siguiente de `LETTERS` (el último pasa al primero)."""
    return LETTERS[(LETTERS.index(text[0]) + 1) % len(LETTERS)] + text[1:]


def _start_runs(repository: PlateRepository, start: datetime) -> None:
    for n in range(1, _DEMO_RUNS + 1):
        repository.start_run(
            RunStart(
                hashlib.sha256(f"demo-{n}".encode()).hexdigest(),
                DEMO_PROFILES[n - 1],
                VideoInfo(1920, 1080, 0, 60_000 * n, 30.0, "h264"),
                start + timedelta(hours=n),
            )
        )


def _build_plate(rng: random.Random, i: int, texto: str) -> ConsolidatedPlate:
    """Construye la placa consolidada de un avistamiento sintético."""
    num = rng.randint(2, 8)
    agreement = round(rng.uniform(0.5, 1.0), 2)
    if i % 8 in {3, 4}:
        confidence = round(rng.uniform(0.90, 0.99), 3)
        return ConsolidatedPlate(texto, confidence, agreement, num, ReviewStatus.CONFIRMED, (), ())
    razon = list(UnverifiedReason)[i % 8]
    guardado = _shifted(texto) if i % 8 == _K_CORRECTED else texto
    confidence = round(rng.uniform(0.55, 0.89), 3)
    return ConsolidatedPlate(
        guardado, confidence, agreement, num, ReviewStatus.UNVERIFIED, (razon,), ()
    )


def _review(
    repository: PlateRepository, sighting_id: int, k: int, texto: str, start: datetime
) -> None:
    reviewed_at = start + timedelta(days=1)
    if k == _K_CORRECTED:
        repository.record_review(sighting_id, ReviewStatus.CORRECTED, texto, reviewed_at)
    elif k == _K_REJECTED:
        repository.record_review(sighting_id, ReviewStatus.REJECTED, None, reviewed_at)
    elif k == _K_ILLEGIBLE:
        repository.record_review(sighting_id, ReviewStatus.ILLEGIBLE, None, reviewed_at)


def _seed_sighting(
    repository: PlateRepository,
    crop_store: CropStore,
    rng: random.Random,
    i: int,
    start: datetime,
) -> tuple[int, Sighting]:
    """Guarda el avistamiento `i` y su revisión; devuelve su id y la entidad guardada."""
    run_id = i // 8 + 1
    vehicle_type = VehicleType.MOTORCYCLE if i % 5 == _MOTORCYCLE_REMAINDER else VehicleType.CAR
    texto = plate_text(rng, vehicle_type)
    first = i % 8 * 7000
    last = first + rng.randint(500, 4000)
    plate = _build_plate(rng, i, texto)
    crop_ref = crop_store.save(render_plate(plate.text))
    quality = CropQuality(
        300, 100, round(rng.uniform(20.0, 200.0), 1), round(rng.uniform(20.0, 80.0), 1)
    )
    sighting = Sighting(
        run_id,
        i,
        first,
        last,
        vehicle_type,
        plate,
        crop_ref,
        start + timedelta(hours=run_id),
        quality,
    )
    sighting_id = repository.save_sighting(sighting)
    _review(repository, sighting_id, i % 8, texto, start)
    return sighting_id, sighting


def _seed_duplicate(
    repository: PlateRepository, track_id: int, original: Sighting
) -> tuple[int, Sighting]:
    """Guarda un duplicado sin confirmar de `original` y devuelve su id y la entidad."""
    plate = ConsolidatedPlate(
        original.plate.text,
        0.6,
        0.6,
        2,
        ReviewStatus.UNVERIFIED,
        original.plate.reasons,
        (),
    )
    duplicate = Sighting(
        original.run_id,
        track_id,
        60_000,
        61_000,
        original.vehicle_type,
        plate,
        original.crop_ref,
        original.created_at,
        original.quality,
    )
    return repository.save_sighting(duplicate), duplicate


def _finish_runs(repository: PlateRepository, saved: list[Sighting], start: datetime) -> None:
    for n in range(1, _DEMO_RUNS + 1):
        of_run = [s for s in saved if s.run_id == n]
        confirmed = sum(1 for s in of_run if s.plate.status is ReviewStatus.CONFIRMED)
        unconfirmed = sum(1 for s in of_run if s.plate.status is ReviewStatus.UNVERIFIED)
        total = confirmed + unconfirmed
        stats = RunStats(
            1800 * n, 900 * n, total + 2, confirmed, unconfirmed, 2, 50_000 * n, 60_000 * n
        )
        repository.finish_run(n, stats, start + timedelta(hours=n, minutes=1), True)


def seed_demo(config: AppConfig, keys: KeyProvider) -> None:
    """Siembra la BD y los recortes de demo con datos sintéticos y deterministas.

    Args:
        config: configuración con la raíz de demo.
        keys: proveedor de la clave de demo.
    """
    rng = random.Random(DEMO_SEED)  # noqa: S311 — datos de demo deterministas, no criptográficos (spec 069)
    start = demo_start(datetime.now(UTC))
    repository = composition.build_repository(config, keys)
    crop_store = composition.build_crop_store(config, keys)
    try:
        _start_runs(repository, start)
        seeded = [_seed_sighting(repository, crop_store, rng, i, start) for i in range(40)]
        id40, dup40 = _seed_duplicate(repository, 40, seeded[1][1])
        id41, dup41 = _seed_duplicate(repository, 41, seeded[9][1])
        repository.mark_duplicates([(id40, seeded[1][0]), (id41, seeded[9][0])])
        saved = [sighting for _, sighting in seeded] + [dup40, dup41]
        _finish_runs(repository, saved, start)
    finally:
        repository.close()


def demo_runner(config: AppConfig, keys: KeyProvider) -> JobRunner:
    """Crea el runner simulado del modo demo.

    Args:
        config: configuración con la raíz de demo.
        keys: proveedor de la clave de demo.

    Returns:
        La función que simula el procesamiento y devuelve el `run_id`.
    """

    def run(video: Path, profile: str, reporter: ProgressReporter) -> int:
        for paso in range(1, 21):
            if reporter.cancel_requested():
                raise ProcessingCancelledError("procesamiento cancelado por el operador")
            reporter.report(ProgressUpdate(paso * 30, paso * 15, paso * 1000, 20_000, paso // 4))
            time.sleep(0.2)
        repository = composition.build_repository(config, keys)
        try:
            run_id = repository.start_run(
                RunStart(
                    sha256_file(video),
                    profile,
                    VideoInfo(1920, 1080, 0, 20_000, 30.0, "h264"),
                    datetime.now(UTC),
                )
            )
            stats = RunStats(600, 300, 0, 0, 0, 0, 4000, 20_000)
            repository.finish_run(run_id, stats, datetime.now(UTC), True)
            return run_id
        finally:
            repository.close()

    return run
