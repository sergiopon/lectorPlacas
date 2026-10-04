"""Adaptador de tracker BoT-SORT con compensación de movimiento de cámara.

Envuelve `trackers.BoTSORTTracker` 2.6.0 detrás del puerto `Tracker`: traduce las
detecciones del dominio a `supervision.Detections` y de vuelta, y pasa el
timestamp en segundos para soportar fps variable.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias, cast

import cv2
import numpy as np
import supervision as sv
from trackers import BoTSORTTracker

from lector_placas.application.ports import ImageBGR
from lector_placas.domain.entities import BoundingBox, TrackedVehicle, VehicleDetection, VehicleType
from lector_placas.domain.errors import TrackingError

logger = logging.getLogger(__name__)

CLASS_ORDER: Final[tuple[VehicleType, ...]] = (
    VehicleType.CAR,
    VehicleType.MOTORCYCLE,
    VehicleType.BUS,
    VehicleType.TRUCK,
)

CmcMethod: TypeAlias = Literal["orb", "sift", "sparseOptFlow", "ecc"]  # noqa: UP040

_MS_PER_SECOND = 1000.0
_UNCONFIRMED_TRACK_ID = -1


@dataclass(frozen=True, slots=True)
class TrackerSettings:
    """Parámetros de `trackers.BoTSORTTracker` expuestos en configuración.

    Attributes:
        lost_track_buffer: cantidad de frames que un track perdido se conserva antes de cerrarse.
        frame_rate: fps de referencia del video.
        track_activation_threshold: confianza mínima para activar un track nuevo.
        minimum_consecutive_frames: detecciones consecutivas necesarias para confirmar un track.
        minimum_iou_threshold_first_assoc: IoU mínimo en la primera asociación.
        minimum_iou_threshold_second_assoc: IoU mínimo en la segunda asociación.
        minimum_iou_threshold_unconfirmed_assoc: IoU mínimo al asociar tracks no confirmados.
        high_conf_det_threshold: umbral que separa detecciones de alta y baja confianza.
        cmc_method: método de compensación de movimiento de cámara.
        cmc_downscale: factor de reducción de la imagen para el cálculo de CMC.
        enable_cmc: activa la compensación de movimiento de cámara.
    """

    lost_track_buffer: int
    frame_rate: float
    track_activation_threshold: float
    minimum_consecutive_frames: int
    minimum_iou_threshold_first_assoc: float
    minimum_iou_threshold_second_assoc: float
    minimum_iou_threshold_unconfirmed_assoc: float
    high_conf_det_threshold: float
    cmc_method: str
    cmc_downscale: int
    enable_cmc: bool = True


def to_supervision(detections: Sequence[VehicleDetection]) -> sv.Detections:
    """Convierte detecciones del dominio al formato que consume `trackers`.

    Args:
        detections: detecciones de vehículos del frame actual.

    Returns:
        `sv.Detections` con `xyxy` y `confidence` en float32 y `class_id` con el índice del tipo
        de vehículo en `CLASS_ORDER`; vacío si no hay detecciones.
    """
    if not detections:
        return sv.Detections.empty()
    boxes = np.array(
        [[d.box.x1, d.box.y1, d.box.x2, d.box.y2] for d in detections], dtype=np.float32
    )
    confidences = np.array([d.confidence for d in detections], dtype=np.float32)
    class_ids = np.array([CLASS_ORDER.index(d.vehicle_type) for d in detections], dtype=int)
    return sv.Detections(xyxy=boxes, confidence=confidences, class_id=class_ids)


def from_supervision(tracked: sv.Detections) -> list[TrackedVehicle]:
    """Convierte las detecciones con `tracker_id` al formato del dominio.

    Args:
        tracked: salida de `BoTSORTTracker.update`.

    Returns:
        Un `TrackedVehicle` por detección con `tracker_id` confirmado (≥ 0); lista vacía si no hay
        `tracker_id` asignado.
    """
    tracker_ids = tracked.tracker_id
    confidences = tracked.confidence
    class_ids = tracked.class_id
    if tracker_ids is None or confidences is None or class_ids is None:
        return []
    vehicles: list[TrackedVehicle] = []
    for index in range(len(tracked)):
        track_id = int(tracker_ids[index])
        if track_id < 0:
            continue
        row = tracked.xyxy[index]
        box = BoundingBox(float(row[0]), float(row[1]), float(row[2]), float(row[3]))
        vehicles.append(
            TrackedVehicle(
                track_id=track_id,
                box=box,
                confidence=float(confidences[index]),
                vehicle_type=CLASS_ORDER[int(class_ids[index])],
            )
        )
    return vehicles


class BotSortTracker:
    """Tracker BoT-SORT, con la CMC según `TrackerSettings.enable_cmc`, detrás del puerto `Tracker`."""  # noqa: E501

    def __init__(self, settings: TrackerSettings) -> None:
        """Inicializa el tracker subyacente con los parámetros recibidos.

        Args:
            settings: parámetros del tracker BoT-SORT.
        """
        self._tracker = BoTSORTTracker(
            lost_track_buffer=settings.lost_track_buffer,
            frame_rate=settings.frame_rate,
            track_activation_threshold=settings.track_activation_threshold,
            minimum_consecutive_frames=settings.minimum_consecutive_frames,
            minimum_iou_threshold_first_assoc=settings.minimum_iou_threshold_first_assoc,
            minimum_iou_threshold_second_assoc=settings.minimum_iou_threshold_second_assoc,
            minimum_iou_threshold_unconfirmed_assoc=settings.minimum_iou_threshold_unconfirmed_assoc,
            high_conf_det_threshold=settings.high_conf_det_threshold,
            enable_cmc=settings.enable_cmc,
            cmc_method=cast("CmcMethod", settings.cmc_method),
            cmc_downscale=settings.cmc_downscale,
            instant_first_frame_activation=True,
        )

    def update(
        self, detections: Sequence[VehicleDetection], image: ImageBGR, timestamp_ms: int
    ) -> list[TrackedVehicle]:
        """Asigna un `track_id` a cada detección del frame actual.

        Debe invocarse en todos los frames, incluso sin detecciones, para que el tracker envejezca
        los tracks abiertos.

        Args:
            detections: detecciones de vehículos del frame actual.
            image: frame BGR completo, usado para la compensación de movimiento de cámara.
            timestamp_ms: timestamp del frame en milisegundos.

        Returns:
            Los vehículos seguidos con `tracker_id` confirmado.

        Raises:
            TrackingError: si el tracker subyacente falla al procesar el frame.
        """
        try:
            result = self._tracker.update(
                to_supervision(detections),
                frame=image,
                timestamp=timestamp_ms / _MS_PER_SECOND,
            )
        except (ValueError, IndexError, cv2.error) as exc:
            raise TrackingError("fallo del tracker") from exc
        return from_supervision(result)

    def reset(self) -> None:
        """Descarta todos los tracks y reinicia los contadores de IDs."""
        self._tracker.reset()
