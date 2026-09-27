"""Sesión de la GUI: abre la base de datos, purga por retención y expone los puertos."""

from __future__ import annotations

from dataclasses import dataclass

from lector_placas.application.ports import (
    Clock,
    CropStore,
    ExportStore,
    KeyProvider,
    PlateRepository,
    SightingBrowser,
)
from lector_placas.application.purge_expired import PurgeResult
from lector_placas.cli import composition
from lector_placas.domain.errors import LectorPlacasError
from lector_placas.infrastructure.clock import SystemClock
from lector_placas.infrastructure.config import AppConfig


@dataclass(slots=True)
class GuiSession:
    """Puertos abiertos por la GUI durante toda la vida de la ventana principal."""

    config: AppConfig
    keys: KeyProvider
    clock: Clock
    repository: PlateRepository
    browser: SightingBrowser
    crop_store: CropStore
    export_store: ExportStore

    def close(self) -> None:
        """Cierra la base de datos de la sesión.

        Postcondiciones:
            Repositorio cerrado; idempotente.
        """
        self.repository.close()


def open_session(config: AppConfig, keys: KeyProvider) -> tuple[GuiSession, PurgeResult]:
    """Abre la sesión de la GUI y purga por retención los datos vencidos (SEG-03).

    Args:
        config: configuración de la aplicación.
        keys: proveedor de la clave maestra, ya leída antes de bloquear la red.

    Returns:
        La sesión abierta y el resultado de la purga inicial.

    Raises:
        LectorPlacasError: si falla la construcción de algún adaptador; en ese caso el
            repositorio ya abierto se cierra antes de propagar el error.
    """
    clock = SystemClock()
    repository = composition.build_repository(config, keys)
    try:
        crop_store = composition.build_crop_store(config, keys)
        export_store = composition.build_export_store(config)
        purge = composition.build_purge(
            config, repository, crop_store, export_store, clock
        ).execute()
        browser = repository.browser()
    except LectorPlacasError:
        repository.close()
        raise
    return (
        GuiSession(config, keys, clock, repository, browser, crop_store, export_store),
        purge,
    )
