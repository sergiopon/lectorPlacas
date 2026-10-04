"""Sesión de la web: abre la base de datos, purga por retención y expone los puertos."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from lector_placas.application.ports import (
    Clock,
    CropStore,
    ExportStore,
    KeyProvider,
    PlateRepository,
    SightingBrowser,
)
from lector_placas.cli import composition
from lector_placas.domain.errors import LectorPlacasError
from lector_placas.infrastructure.clock import SystemClock
from lector_placas.infrastructure.config import AppConfig


@dataclass(slots=True)
class WebSession:
    """Puertos abiertos por la web durante toda la vida de la aplicación."""

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


type SessionFactory = Callable[[AppConfig, KeyProvider], WebSession]


def open_web_session(config: AppConfig, keys: KeyProvider) -> WebSession:
    """Abre la sesión de la web y purga por retención los datos vencidos (SEG-03).

    Args:
        config: configuración de la aplicación.
        keys: proveedor de la clave maestra, ya leída antes de bloquear la red.

    Returns:
        La sesión abierta.

    Raises:
        LectorPlacasError: si falla la construcción de algún adaptador; en ese caso el
            repositorio ya abierto se cierra antes de propagar el error.
    """
    clock = SystemClock()
    repository = composition.build_repository(config, keys)
    try:
        crop_store = composition.build_crop_store(config, keys)
        export_store = composition.build_export_store(config)
        composition.build_purge(config, repository, crop_store, export_store, clock).execute()
        browser = repository.browser()
    except LectorPlacasError:
        repository.close()
        raise
    return WebSession(config, keys, clock, repository, browser, crop_store, export_store)
