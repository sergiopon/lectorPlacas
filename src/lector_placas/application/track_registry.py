"""Registro en memoria del ciclo de vida de los tracks, sus lecturas y su mejor recorte."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from lector_placas.application.ports import ImageBGR
from lector_placas.domain.entities import PlateReading, TrackedVehicle, VehicleType
from lector_placas.domain.errors import ConfigurationError, InvalidEntityError

_VEHICLE_TYPE_ORDER: Final[dict[VehicleType, int]] = {
    vehicle_type: index for index, vehicle_type in enumerate(VehicleType)
}


@dataclass(frozen=True, slots=True, eq=False)
class FinalizedTrack:
    """Track extraído del registro, con su tipo consolidado, lecturas y mejor recorte."""

    track_id: int
    first_seen_ms: int
    last_seen_ms: int
    vehicle_type: VehicleType
    readings: tuple[PlateReading, ...]
    best_crop: ImageBGR | None


@dataclass(slots=True)
class _TrackState:
    """Estado mutable de un track mientras sigue activo en el registro."""

    first_seen_ms: int
    last_seen_ms: int
    type_votes: dict[VehicleType, int]
    type_confidence: dict[VehicleType, float]
    readings: list[PlateReading]
    best_crop: ImageBGR | None
    best_score: float


class TrackRegistry:
    """Gestiona el ciclo de vida de los tracks observados en un video."""

    def __init__(self, max_readings_per_track: int) -> None:
        """Crea el registro vacío con el límite de lecturas por track.

        Args:
            max_readings_per_track: número máximo de lecturas por track.

        Raises:
            ConfigurationError: Si `max_readings_per_track` es menor que 1.
        """
        if max_readings_per_track < 1:
            raise ConfigurationError(
                f"max_readings_per_track debe ser >= 1: {max_readings_per_track}"
            )
        self._max_readings_per_track = max_readings_per_track
        self._tracks: dict[int, _TrackState] = {}

    @property
    def active_count(self) -> int:
        """Número de tracks actualmente en el registro."""
        return len(self._tracks)

    def observe(self, tracked: Sequence[TrackedVehicle], timestamp_ms: int) -> None:
        """Registra la observación de los vehículos en el frame indicado.

        Args:
            tracked: vehículos seguidos en el frame, con su tipo y confianza.
            timestamp_ms: marca de tiempo del frame en milisegundos.
        """
        for vehicle in tracked:
            state = self._tracks.get(vehicle.track_id)
            if state is None:
                state = _new_state(timestamp_ms)
                self._tracks[vehicle.track_id] = state
            state.last_seen_ms = timestamp_ms
            state.type_votes[vehicle.vehicle_type] = (
                state.type_votes.get(vehicle.vehicle_type, 0) + 1
            )
            state.type_confidence[vehicle.vehicle_type] = (
                state.type_confidence.get(vehicle.vehicle_type, 0.0) + vehicle.confidence
            )

    def needs_reading(self, track_id: int) -> bool:
        """Indica si el track existe y por lo tanto sigue admitiendo lecturas.

        Args:
            track_id: identificador del track consultado.

        Returns:
            `True` si y solo si el track está activo en el registro, tenga o no ya el máximo
            de lecturas: una lectura nueva puede reemplazar a la peor guardada.
        """
        return track_id in self._tracks

    def is_full(self, track_id: int) -> bool:
        """Indica si el track existe y ya alcanzó el máximo de lecturas guardadas.

        Args:
            track_id: identificador del track consultado.

        Returns:
            `True` si el track existe y tiene ya `max_readings_per_track` lecturas; `False`
            si no existe o tiene menos.
        """
        state = self._tracks.get(track_id)
        return state is not None and len(state.readings) >= self._max_readings_per_track

    def add_reading(self, reading: PlateReading, crop: ImageBGR) -> None:
        """Añade una lectura al track o la descarta si es peor que las ya guardadas.

        Con el track por debajo del máximo, la lectura se añade. Con el track lleno, la
        lectura reemplaza a la peor guardada (menor ancho de placa y, a igual ancho, menor
        nitidez; entre empates la más antigua) solo si es estrictamente mejor; si no, se
        descarta. En cualquier caso se evalúa como candidata al mejor recorte del track.

        Args:
            reading: lectura OCR del track.
            crop: recorte de placa asociado a la lectura.

        Raises:
            InvalidEntityError: Si el track no existe.
        """
        state = self._tracks.get(reading.track_id)
        if state is None:
            raise InvalidEntityError(f"track inexistente: {reading.track_id}")
        if len(state.readings) < self._max_readings_per_track:
            state.readings.append(reading)
        else:
            worst_index = min(
                range(len(state.readings)),
                key=lambda index: (
                    *_reading_quality(state.readings[index]),
                    state.readings[index].timestamp_ms,
                ),
            )
            if _reading_quality(reading) > _reading_quality(state.readings[worst_index]):
                state.readings[worst_index] = reading
        score = reading.quality_score * reading.mean_confidence
        if state.best_crop is None or score > state.best_score:
            state.best_crop = crop.copy()
            state.best_score = score

    def pop_inactive(self, now_ms: int, inactive_after_ms: int) -> list[FinalizedTrack]:
        """Extrae los tracks sin observaciones durante más de `inactive_after_ms`.

        Args:
            now_ms: marca de tiempo actual en milisegundos.
            inactive_after_ms: tiempo de inactividad que finaliza un track.

        Returns:
            Tracks finalizados ordenados por `track_id`.
        """
        expired = [
            track_id
            for track_id, state in self._tracks.items()
            if now_ms - state.last_seen_ms > inactive_after_ms
        ]
        return self._extract(expired)

    def pop_all(self) -> list[FinalizedTrack]:
        """Extrae todos los tracks del registro.

        Returns:
            Tracks finalizados ordenados por `track_id`.
        """
        return self._extract(list(self._tracks))

    def _extract(self, track_ids: Sequence[int]) -> list[FinalizedTrack]:
        """Saca del registro los tracks indicados y los finaliza ordenados por `track_id`."""
        finalized: list[FinalizedTrack] = []
        for track_id in sorted(track_ids):
            state = self._tracks.pop(track_id)
            finalized.append(
                FinalizedTrack(
                    track_id=track_id,
                    first_seen_ms=state.first_seen_ms,
                    last_seen_ms=state.last_seen_ms,
                    vehicle_type=_dominant_type(state),
                    readings=tuple(
                        sorted(state.readings, key=lambda r: (r.timestamp_ms, r.frame_index))
                    ),
                    best_crop=state.best_crop,
                )
            )
        return finalized


def _new_state(timestamp_ms: int) -> _TrackState:
    """Crea el estado inicial de un track visto por primera vez."""
    return _TrackState(
        first_seen_ms=timestamp_ms,
        last_seen_ms=timestamp_ms,
        type_votes={},
        type_confidence={},
        readings=[],
        best_crop=None,
        best_score=0.0,
    )


def _reading_quality(reading: PlateReading) -> tuple[float, float]:
    """Clave de calidad de una lectura: ancho de la placa y, a igual ancho, su nitidez."""
    return (reading.plate_box.width, reading.quality_score)


def _dominant_type(state: _TrackState) -> VehicleType:
    """Elige el tipo con más votos, desempatando por confianza y orden de declaración."""
    return min(
        state.type_votes,
        key=lambda vehicle_type: (
            -state.type_votes[vehicle_type],
            -state.type_confidence[vehicle_type],
            _VEHICLE_TYPE_ORDER[vehicle_type],
        ),
    )
