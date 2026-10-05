from __future__ import annotations

import socket
import tempfile
from pathlib import Path
from typing import Any

import pytest

from lector_placas.domain.errors import ConfigurationError, KeyUnavailableError
from lector_placas.web.app import (
    KEY_HINT,
    _serve,
    bind_host,
    bind_socket,
    key_hint,
    launch_url,
    main,
    parse_args,
    public_port,
)
from tests.fixtures.fakes import FakeKeyProvider

ROOT = Path(__file__).resolve().parents[3]


class Recorder:
    """Registra las llamadas de los dobles instalados por `install_fakes`."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.create_app_kwargs: dict[str, Any] = {}
        self.browser_urls: list[str] = []
        self.server_hosts: list[str] = []
        self.server_ports: list[int] = []
        self.configs: list[dict[str, Any]] = []


class FakeConfig:
    """Sustituye a `uvicorn.Config` registrando sus argumentos."""

    recorder: Recorder

    def __init__(self, app: object, **kwargs: Any) -> None:
        type(self).recorder.configs.append(kwargs)


class FakeServer:
    """Sustituye a `uvicorn.Server`: registra el socket y vuelve."""

    recorder: Recorder

    def __init__(self, config: object) -> None:
        self.config = config

    def run(self, sockets: list[socket.socket]) -> None:
        host, port = sockets[0].getsockname()
        type(self).recorder.server_hosts.append(host)
        type(self).recorder.server_ports.append(port)


def install_fakes(monkeypatch: pytest.MonkeyPatch, keys: FakeKeyProvider | None = None) -> Recorder:
    recorder = Recorder()
    FakeConfig.recorder = recorder
    FakeServer.recorder = recorder
    provider = keys if keys is not None else FakeKeyProvider()

    def fake_create_app(*args: Any, **kwargs: Any) -> object:
        recorder.events.append("create_app")
        recorder.create_app_kwargs = kwargs
        return object()

    def fake_block_network() -> None:
        recorder.events.append("block_network")

    monkeypatch.chdir(ROOT)
    monkeypatch.setattr("lector_placas.web.app.configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "lector_placas.web.app.composition.build_key_provider", lambda _flag: provider
    )
    monkeypatch.setattr("lector_placas.web.app.network_guard.block_network", fake_block_network)
    monkeypatch.setattr("lector_placas.web.app.create_app", fake_create_app)
    monkeypatch.setattr("lector_placas.web.app.webbrowser.open", recorder.browser_urls.append)
    monkeypatch.setattr("lector_placas.web.app.uvicorn.Server", FakeServer)
    monkeypatch.setattr("lector_placas.web.app.uvicorn.Config", FakeConfig)
    return recorder


def check_parse_args_custom() -> None:
    args = parse_args(["--port", "9000", "--no-browser"])
    assert args.port == 9000
    assert args.no_browser is True


def check_bind_socket_invalid_port() -> None:
    with pytest.raises(ValueError, match="puerto inválido: 70000"):
        bind_socket(70000)


def test_parse_args_defaults() -> None:
    args = parse_args([])
    assert args.config == Path("config/lector.yaml")
    assert args.port == 0
    assert args.no_browser is False
    check_parse_args_custom()


def test_bind_socket_is_loopback() -> None:
    sock = bind_socket(0)
    try:
        assert sock.getsockname()[0] == "127.0.0.1"
        assert sock.getsockname()[1] > 0
    finally:
        sock.close()
    check_bind_socket_invalid_port()


def test_bind_host_container(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LECTOR_IN_CONTAINER", "1")
    assert bind_host() == "0.0.0.0"  # noqa: S104 — excepción de contenedor de SEG-28
    monkeypatch.setenv("LECTOR_IN_CONTAINER", "true")
    assert bind_host() == "127.0.0.1"
    monkeypatch.delenv("LECTOR_IN_CONTAINER")
    assert bind_host() == "127.0.0.1"


def test_launch_url() -> None:
    assert launch_url(8765, "abc") == "http://127.0.0.1:8765/auth?token=abc"


def check_main_opens_browser_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = install_fakes(monkeypatch)
    assert main([]) == 0
    out = capsys.readouterr().out
    assert len(recorder.browser_urls) == 1
    assert f"Abra: {recorder.browser_urls[0]}\n" in out


def test_main_happy_path(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = install_fakes(monkeypatch)
    assert main(["--no-browser"]) == 0
    out = capsys.readouterr().out
    assert recorder.events == ["block_network", "create_app"]
    assert recorder.server_hosts == ["127.0.0.1"]
    assert recorder.browser_urls == []
    assert "Abra: http://127.0.0.1:" in out
    assert "/auth?token=" in out
    assert recorder.create_app_kwargs["static_dir"] == ROOT / "frontend" / "dist"
    check_main_opens_browser_by_default(monkeypatch, capsys)


def test_uvicorn_config_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = install_fakes(monkeypatch)
    assert main(["--no-browser"]) == 0
    assert len(recorder.configs) == 1
    flags = recorder.configs[0]
    assert flags["host"] == "127.0.0.1"
    assert flags["access_log"] is False
    assert flags["server_header"] is False
    assert flags["date_header"] is False
    assert flags["lifespan"] == "on"


class MissingKeyProvider(FakeKeyProvider):
    def master_key(self) -> bytes:
        raise KeyUnavailableError("sin clave")


def test_main_key_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = install_fakes(monkeypatch, MissingKeyProvider())
    assert main([]) == 1
    err = capsys.readouterr().err
    assert "lector-web: sin clave" in err
    assert KEY_HINT in err
    assert "block_network" not in recorder.events


def test_main_port_busy(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_fakes(monkeypatch)

    def busy(port: int) -> socket.socket:
        raise OSError("ocupado")

    monkeypatch.setattr("lector_placas.web.app.bind_socket", busy)
    assert main(["--port", "8765"]) == 1
    assert "lector-web: no se pudo abrir el puerto 8765" in capsys.readouterr().err


def check_demo_root(demo_root: Path) -> None:
    assert str(demo_root).startswith(tempfile.gettempdir())
    assert "lector-demo-" in str(demo_root)
    assert not demo_root.exists()


def test_main_demo_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = install_fakes(monkeypatch)
    seeded: list[Any] = []
    app_configs: list[Any] = []

    def fake_create_app(config: Any, *args: Any, **kwargs: Any) -> object:
        app_configs.append(config)
        recorder.create_app_kwargs = kwargs
        return object()

    monkeypatch.setattr("lector_placas.web.app.create_app", fake_create_app)

    def forbidden_key_provider(_flag: bool) -> FakeKeyProvider:
        raise AssertionError("no debe leerse el keyring en modo demo")

    monkeypatch.setattr(
        "lector_placas.web.app.composition.build_key_provider", forbidden_key_provider
    )
    monkeypatch.setattr(
        "lector_placas.web.app.seed_demo", lambda config, keys: seeded.append(config)
    )
    assert main(["--demo", "--no-browser"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Modo demo: datos sintéticos en una carpeta temporal")
    assert recorder.create_app_kwargs["static_dir"] == ROOT / "frontend" / "dist"
    assert len(seeded) == 1
    assert app_configs == seeded
    check_demo_root(app_configs[0].root_dir)


def test_public_port_outside_container(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LECTOR_IN_CONTAINER", raising=False)
    monkeypatch.setenv("LECTOR_PUBLIC_PORT", "9000")
    assert public_port(8765) == 8765


def test_public_port_in_container(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LECTOR_IN_CONTAINER", "1")
    monkeypatch.setenv("LECTOR_PUBLIC_PORT", "9000")
    assert public_port(8765) == 9000
    monkeypatch.setenv("LECTOR_PUBLIC_PORT", "")
    assert public_port(8765) == 8765
    monkeypatch.delenv("LECTOR_PUBLIC_PORT")
    assert public_port(8765) == 8765


def test_public_port_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LECTOR_IN_CONTAINER", "1")
    for value in ("0", "65536", "9000a", " 9000"):
        monkeypatch.setenv("LECTOR_PUBLIC_PORT", value)
        with pytest.raises(ConfigurationError) as info:
            public_port(8765)
        assert str(info.value) == "LECTOR_PUBLIC_PORT debe ser un entero entre 1 y 65535"


def test_key_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LECTOR_KEY_FILE", "/app/keys/lector_key")
    assert key_hint() == "Cree la clave con: lector key init-file /app/keys/lector_key"
    monkeypatch.delenv("LECTOR_KEY_FILE")
    assert key_hint() == "Cree la clave con: lector key init"


def test_serve_uses_public_port(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LECTOR_IN_CONTAINER", "1")
    monkeypatch.setenv("LECTOR_PUBLIC_PORT", "9000")
    received: dict[str, Any] = {}

    def fake_create_app(*args: Any, **kwargs: Any) -> object:
        received["allowed_hosts"] = args[3]
        return object()

    class DoubleServer:
        def __init__(self, config: object) -> None:
            self.config = config

        def run(self, sockets: list[socket.socket]) -> None:
            return None

    monkeypatch.setattr("lector_placas.web.app.create_app", fake_create_app)
    monkeypatch.setattr("lector_placas.web.app.uvicorn.Server", DoubleServer)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    assert _serve(object(), FakeKeyProvider(), sock, True, ROOT) == 0  # type: ignore[arg-type]
    assert received["allowed_hosts"] == frozenset({"127.0.0.1:9000", "localhost:9000"})
    assert "http://127.0.0.1:9000/auth?token=" in capsys.readouterr().out
