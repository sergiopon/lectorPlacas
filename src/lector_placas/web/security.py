"""Seguridad local de la web (SEG-28): `Host`, token de arranque, cookie de sesión y cabeceras."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Final

from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import FastAPI, Request, Response

SESSION_COOKIE: Final[str] = "lector_session"
CSP: Final[str] = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; "
    "base-uri 'none'; form-action 'self'"
)


class SessionAuth:
    """Intercambia el token de arranque (un solo uso) por una cookie de sesión."""

    def __init__(self, launch_token: str) -> None:
        """Guarda el token de arranque.

        Args:
            launch_token: token de un solo uso entregado al navegador al arrancar.
        """
        self._launch_token = launch_token
        self._used = False
        self._session: str | None = None

    def exchange(self, token: str) -> str | None:
        """Canjea el token de arranque por una sesión.

        Args:
            token: token presentado por el navegador.

        Returns:
            La sesión nueva, o `None` si el token ya se usó o no coincide.
        """
        if self._used or not secrets.compare_digest(
            token.encode("utf-8"), self._launch_token.encode("utf-8")
        ):
            return None
        self._used = True
        self._session = secrets.token_urlsafe(32)
        return self._session

    def is_valid(self, cookie: str | None) -> bool:
        """Indica si `cookie` es la sesión generada.

        Args:
            cookie: valor de la cookie de sesión, si la hay.

        Returns:
            `True` solo si coincide con la sesión generada.
        """
        return (
            cookie is not None
            and self._session is not None
            and secrets.compare_digest(cookie.encode("utf-8"), self._session.encode("utf-8"))
        )


def allowed_hosts_for(port: int) -> frozenset[str]:
    """Devuelve los valores `Host` permitidos para `port`."""
    return frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})


def _with_headers(response: Response, path: str) -> Response:
    """Añade las cabeceras de seguridad a `response`."""
    response.headers["Content-Security-Policy"] = CSP
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def install_security(app: FastAPI, auth: SessionAuth, allowed_hosts: frozenset[str]) -> None:
    """Registra el middleware de seguridad en `app`.

    Args:
        app: aplicación FastAPI.
        auth: autenticación de sesión.
        allowed_hosts: valores `Host` permitidos.
    """

    @app.middleware("http")
    async def security_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if request.headers.get("host") not in allowed_hosts:
            rejected: Response = JSONResponse({"detail": "host no permitido"}, status_code=400)
            return _with_headers(rejected, path)
        if path.startswith("/api/") and not auth.is_valid(request.cookies.get(SESSION_COOKIE)):
            rejected = JSONResponse({"detail": "no autenticado"}, status_code=401)
            return _with_headers(rejected, path)
        return _with_headers(await call_next(request), path)
