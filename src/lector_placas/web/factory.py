"""Fábrica de la aplicación FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.staticfiles import StaticFiles

from lector_placas.application.ports import KeyProvider
from lector_placas.cli import composition
from lector_placas.infrastructure.config import AppConfig
from lector_placas.web.jobs import JobManager, JobRunner, default_runner
from lector_placas.web.media import MediaServices, VideoLocator
from lector_placas.web.routes_actions import router as actions_router
from lector_placas.web.routes_media import router as media_router
from lector_placas.web.routes_read import router
from lector_placas.web.security import SESSION_COOKIE, SessionAuth, install_security
from lector_placas.web.session import SessionFactory, open_web_session

NO_FRONTEND_HTML: Final[str] = (
    '<!doctype html><html lang="es"><meta charset="utf-8"><title>lectorPlacas</title>'
    "<p>Frontend no compilado. Ejecute <code>npm ci &amp;&amp; npm run build</code> en "
    "<code>frontend/</code> y reinicie <code>lector-web</code>.</p></html>"
)


def _include_routers(app: FastAPI) -> None:
    """Registra los routers de lectura y de acciones."""
    app.include_router(router)
    app.include_router(actions_router)
    app.include_router(media_router)


def _install_state(
    app: FastAPI, config: AppConfig, keys: KeyProvider, runner: JobRunner | None
) -> None:
    """Crea los trabajos y los servicios de medios en el estado de la app."""
    app.state.jobs = JobManager(runner if runner is not None else default_runner(config, keys))
    app.state.media = MediaServices(
        VideoLocator(config),
        composition.build_frame_grabber(),
        composition.build_video_source_factory(),
    )


def _mount_frontend(app: FastAPI, static_dir: Path | None) -> None:
    """Monta el frontend compilado o registra un endpoint de no-frontend.

    Args:
        app: aplicación FastAPI.
        static_dir: directorio del frontend compilado, o None.
    """
    if static_dir is not None and (static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    else:

        @app.get("/")
        async def no_frontend() -> Response:
            return HTMLResponse(NO_FRONTEND_HTML)


def create_app(  # noqa: PLR0913, PLR0917 — firma fijada por la spec 068
    config: AppConfig,
    keys: KeyProvider,
    auth: SessionAuth,
    allowed_hosts: frozenset[str],
    session_factory: SessionFactory = open_web_session,
    runner: JobRunner | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    """Crea la aplicación web local.

    Args:
        config: configuración de la aplicación.
        keys: proveedor de la clave maestra.
        auth: autenticación de sesión.
        allowed_hosts: valores `Host` permitidos.
        session_factory: función que abre la sesión al arrancar.
        runner: función que procesa un video; si es `None`, se usa `default_runner`.
        static_dir: directorio del frontend compilado; si no existe `index.html`,
            se sirve un mensaje.

    Returns:
        La aplicación FastAPI con seguridad y endpoints de lectura.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        session = session_factory(config, keys)
        app.state.session = session
        try:
            yield
        finally:
            session.close()

    app = FastAPI(
        title="lectorPlacas",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    _install_state(app, config, keys, runner)
    install_security(app, auth, allowed_hosts)

    @app.exception_handler(RequestValidationError)
    async def invalid_parameter(request: Request, exc: RequestValidationError) -> Response:
        return JSONResponse({"detail": "parámetro inválido"}, status_code=422)

    @app.get("/auth")
    async def exchange_token(token: str = "") -> Response:
        session = auth.exchange(token)
        if session is None:
            return JSONResponse({"detail": "token inválido"}, status_code=403)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE, session, httponly=True, samesite="strict", path="/", secure=False
        )
        return response

    _include_routers(app)
    _mount_frontend(app, static_dir)
    return app
