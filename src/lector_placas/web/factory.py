"""Fábrica de la aplicación FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response

from lector_placas.application.ports import KeyProvider
from lector_placas.infrastructure.config import AppConfig
from lector_placas.web.routes_read import router
from lector_placas.web.security import SESSION_COOKIE, SessionAuth, install_security
from lector_placas.web.session import SessionFactory, open_web_session


def create_app(
    config: AppConfig,
    keys: KeyProvider,
    auth: SessionAuth,
    allowed_hosts: frozenset[str],
    session_factory: SessionFactory = open_web_session,
) -> FastAPI:
    """Crea la aplicación web local.

    Args:
        config: configuración de la aplicación.
        keys: proveedor de la clave maestra.
        auth: autenticación de sesión.
        allowed_hosts: valores `Host` permitidos.
        session_factory: función que abre la sesión al arrancar.

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

    app.include_router(router)
    return app
