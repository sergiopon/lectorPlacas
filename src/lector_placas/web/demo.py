"""Modo demo de lector-web: datos sintéticos en una carpeta temporal."""

from __future__ import annotations

import random
import secrets
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import av
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
DEMO_VIDEOS: Final[tuple[str, ...]] = (
    "demo_parqueadero.webm",
    "demo_calle_1.webm",
    "demo_via_rapida.webm",
    "demo_patrulla.webm",
    "demo_calle_2.webm",
)
VIDEO_SIZE: Final[tuple[int, int]] = (640, 360)
VIDEO_FPS: Final[int] = 10
VIDEO_MS: Final[int] = 62_000
LETTERS: Final[str] = "ABCDEFGHJKLMNPRSTUVWXYZ"
DIGITS: Final[str] = "0123456789"
PLATE_SIZE: Final[tuple[int, int]] = (300, 100)
PLATE_BGR: Final[tuple[int, int, int]] = (0, 204, 255)
_LANE_Y: Final[int] = 300
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
    """Crea la carpeta temporal de demo con la carpeta `videos/` vacía.

    Returns:
        Ruta de la carpeta temporal.
    """
    root = Path(tempfile.mkdtemp(prefix="lector-demo-"))
    root.chmod(0o700)
    videos = root / "videos"
    videos.mkdir()
    videos.chmod(0o700)
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


@dataclass(frozen=True, slots=True)
class _SightingPlan:
    """Plan inmutable de un avistamiento sintético de la demo."""

    run_id: int
    track_id: int
    vehicle_type: VehicleType
    texto: str
    guardado: str
    first: int
    last: int
    plate: ConsolidatedPlate
    quality: CropQuality


def _start_runs(repository: PlateRepository, start: datetime, shas: dict[int, str]) -> None:
    for n in range(1, _DEMO_RUNS + 1):
        repository.start_run(
            RunStart(
                shas[n],
                DEMO_PROFILES[n - 1],
                VideoInfo(VIDEO_SIZE[0], VIDEO_SIZE[1], 0, VIDEO_MS, 10.0, "vp8"),
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


def _plan_sighting(rng: random.Random, i: int, start: datetime) -> _SightingPlan:
    """Planifica el avistamiento `i` sin tocar la BD ni el almacén de recortes.

    Args:
        rng: generador pseudoaleatorio.
        i: índice del avistamiento.
        start: instante base de la demo.

    Returns:
        El plan inmutable del avistamiento.
    """
    run_id = i // 8 + 1
    vehicle_type = VehicleType.MOTORCYCLE if i % 5 == _MOTORCYCLE_REMAINDER else VehicleType.CAR
    texto = plate_text(rng, vehicle_type)
    first = i % 8 * 7000
    last = first + rng.randint(500, 4000)
    plate = _build_plate(rng, i, texto)
    quality = CropQuality(
        300, 100, round(rng.uniform(20.0, 200.0), 1), round(rng.uniform(20.0, 80.0), 1)
    )
    return _SightingPlan(run_id, i, vehicle_type, texto, plate.text, first, last, plate, quality)


def _store_sighting(
    repository: PlateRepository,
    crop_store: CropStore,
    plan: _SightingPlan,
    start: datetime,
) -> tuple[int, Sighting]:
    """Guarda el recorte, el avistamiento y su revisión; devuelve id y entidad."""
    crop_ref = crop_store.save(render_plate(plan.guardado))
    sighting = Sighting(
        plan.run_id,
        plan.track_id,
        plan.first,
        plan.last,
        plan.vehicle_type,
        plan.plate,
        crop_ref,
        start + timedelta(hours=plan.run_id),
        plan.quality,
    )
    sighting_id = repository.save_sighting(sighting)
    _review(repository, sighting_id, plan.track_id % 8, plan.texto, start)
    return sighting_id, sighting


def _finish_runs(repository: PlateRepository, saved: list[Sighting], start: datetime) -> None:
    for n in range(1, _DEMO_RUNS + 1):
        of_run = [s for s in saved if s.run_id == n]
        confirmed = sum(1 for s in of_run if s.plate.status is ReviewStatus.CONFIRMED)
        unconfirmed = sum(1 for s in of_run if s.plate.status is ReviewStatus.UNVERIFIED)
        total = confirmed + unconfirmed
        stats = RunStats(
            1800 * n, 900 * n, total + 2, confirmed, unconfirmed, 2, 50_000 * n, VIDEO_MS
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
        plans = [_plan_sighting(rng, i, start) for i in range(40)]
        plans.append(replace(plans[1], track_id=40, first=60_000, last=61_000))
        plans.append(replace(plans[9], track_id=41, first=60_000, last=61_000))
        shas = _write_demo_videos(config.under_root(Path("videos")), plans)
        _start_runs(repository, start, shas)
        seeded = [_store_sighting(repository, crop_store, plan, start) for plan in plans]
        repository.mark_duplicates([(seeded[40][0], seeded[1][0]), (seeded[41][0], seeded[9][0])])
        saved = [sighting for _, sighting in seeded]
        _finish_runs(repository, saved, start)
    finally:
        repository.close()


def _draw_vehicle(image: ImageBGR, plan: _SightingPlan, timestamp_ms: int) -> None:
    """Dibuja el rectángulo del vehículo y su placa sobre el fotograma."""
    x = int(40 + (timestamp_ms - plan.first) / max(1, plan.last - plan.first) * 410)
    y = 230
    cv2.rectangle(image, (x - 35, y - 70), (x + 185, y + 60), (120, 60, 40), -1)
    plate = cv2.resize(render_plate(plan.guardado), (150, 50))
    image[y : y + 50, x : x + 150] = plate


def _render_frame(plans: Sequence[_SightingPlan], timestamp_ms: int) -> ImageBGR:
    """Pinta el fotograma de la demo en el instante dado."""
    image: ImageBGR = np.full((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), 90, np.uint8)
    for x in range(0, VIDEO_SIZE[0], 80):
        cv2.line(image, (x, _LANE_Y), (x + 40, _LANE_Y), (255, 255, 255), 4)
    for plan in plans:
        if plan.first <= timestamp_ms <= plan.last:
            _draw_vehicle(image, plan, timestamp_ms)
    return image


def _write_video(path: Path, plans: Sequence[_SightingPlan]) -> None:
    """Codifica en WebM el recorrido de los planes de una corrida."""
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libvpx", rate=VIDEO_FPS)
        stream.width, stream.height = VIDEO_SIZE
        stream.pix_fmt = "yuv420p"
        stream.options = {"deadline": "realtime", "cpu-used": "8"}
        for index in range(VIDEO_MS * VIDEO_FPS // 1000):
            frame = av.VideoFrame.from_ndarray(_render_frame(plans, index * 100), format="bgr24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def _write_demo_videos(videos_dir: Path, plans: Sequence[_SightingPlan]) -> dict[int, str]:
    """Escribe un video WebM por corrida y devuelve el SHA-256 de cada uno."""
    shas: dict[int, str] = {}
    for n in range(1, _DEMO_RUNS + 1):
        path = videos_dir / DEMO_VIDEOS[n - 1]
        _write_video(path, [plan for plan in plans if plan.run_id == n])
        path.chmod(0o600)
        shas[n] = sha256_file(path)
    return shas


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
