"""Chequeos no funcionales de nivel F.

Corre el pipeline sobre un video sintético 1080p30 de 60 s (o uno provisto) y verifica:
  1. red bloqueada     → 0 llamadas `connect` a la red (AF_INET/AF_INET6) con strace
  2. permisos          → directorios 0700 y archivos 0600 en data/ y logs/
  3. placas en claro   → 0 coincidencias de PLATE_PATTERN sin enmascarar en logs/
  4. cifrado en reposo → 0 `SQLite format 3` y 0 bytes PNG en claro en data/
  5. velocidad         → speed_factor >= 1.0
  6. VRAM              → pico <= 4096 MiB (por encima de la línea base)
  7. web             → escucha solo en 127.0.0.1; Host ajeno → 400; /api sin sesión → 401

Uso:
    uv run python scripts/nivel_f.py [--video VIDEOS/mi_video.mp4] [--seconds 60] [--regen]

Requisitos previos:
    uv sync --locked
    uv run lector key init            # clave maestra en el keyring
    uv run lector models verify       # modelos descargados y verificados
"""

from __future__ import annotations

import argparse
import http.client
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import av
import numpy as np

from lector_placas.evaluation.vram_monitor import VramMonitor

ROOT = Path(__file__).resolve().parents[1]
VIDEOS_DIR = ROOT / "videos"
DEFAULT_VIDEO = VIDEOS_DIR / "sintetico_1080p30.mp4"
PROFILE = "calle_rapida"

# Misma expresión que logging_setup.PLATE_PATTERN: cualquier texto con forma de placa.
PLATE_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:[A-Z]{3}[0-9]{2}[A-Z0-9]?|[0-9]{3}[A-Z]{3}"
    r"|[A-Z]{2}[0-9]{4}|[RS][0-9]{5}|T[0-9]{4})(?![A-Z0-9])"
)
WEB_URL_RE = re.compile(r"^lectorPlacas web en http://127\.0\.0\.1:(\d+)/$")
SPEED_RE = re.compile(r"velocidad=(\d+(?:\.\d+)?)x|velocidad=(n/d)")

HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
LIMITS = {"speed": 1.0, "vram_mib": 4096}


def _lector_cmd(*args: str) -> list[str]:
    """Invoca la CLI `lector` en este mismo entorno virtual, sin pasar por `uv`."""
    return [
        sys.executable,
        "-c",
        "from lector_placas.cli.main import main; raise SystemExit(main())",
        *args,
    ]


def _synthetic_frame(index: int, width: int, height: int) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:8, :8] = 255  # marca blanca arriba a la izquierda
    image[height - 4 :, :, 2] = (index * 20) % 256
    return image


def generate_video(path: Path, seconds: int) -> None:
    """Genera un video sintético 1080p30 de `seconds` segundos con PyAV (mpeg4)."""
    VIDEOS_DIR.mkdir(exist_ok=True)
    print(f"generando video sintético: {path} ({seconds} s, 1080p30)...")
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=30)
        stream.width = 1920
        stream.height = 1080
        stream.pix_fmt = "yuv420p"
        for index in range(seconds * 30):
            frame = av.VideoFrame.from_ndarray(_synthetic_frame(index, 1920, 1080), format="bgr24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    print(f"  listo: {path} ({path.stat().st_size / 1e6:.1f} MB)")


def check_network_blocked(video: Path) -> tuple[bool, str]:
    """Cuenta las llamadas `connect` a la red durante `lector process` con strace."""
    if shutil.which("strace") is None:
        return False, "strace no disponible (sudo apt install strace); omitido"
    log = ROOT / "logs" / "strace_connect.log"
    log.parent.mkdir(exist_ok=True)
    # strace crea su log con 0644; se pre-crea en 0600 (strace conserva el modo del
    # archivo existente).
    log.unlink(missing_ok=True)
    log.touch(mode=0o600)
    cmd = [
        "strace",
        "-f",
        "-e",
        "trace=connect",
        "-o",
        str(log),
        *_lector_cmd("process", str(video), "--profile", PROFILE),
    ]
    subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    if not log.exists():
        return False, "no se generó el log de strace"
    log.chmod(0o600)
    connects = sum(
        1
        for line in log.read_text(encoding="utf-8").splitlines()
        if "connect(" in line and ("AF_INET" in line or "AF_INET6" in line)
    )
    if connects == 0:
        return True, "0 llamadas connect a la red"
    return False, f"{connects} llamadas connect a la red"


def check_permissions() -> tuple[bool, str]:
    """Verifica directorios 0700 y archivos 0600 en data/ y logs/."""
    issues: list[str] = []
    for name in ("data", "logs"):
        base = ROOT / name
        if not base.exists():
            continue
        for path in base.rglob("*"):
            mode = path.stat().st_mode & 0o777
            expected = 0o700 if path.is_dir() else 0o600
            if mode != expected:
                issues.append(f"{path.relative_to(ROOT)} = {oct(mode)} (esperado {oct(expected)})")
    if issues:
        return False, "; ".join(issues)
    return True, "permisos correctos (dirs 0700, archivos 0600)"


def check_plates_in_logs() -> tuple[bool, str]:
    """Ninguna placa en claro en logs/."""
    logs = ROOT / "logs"
    found: list[str] = []
    if logs.exists():
        for path in logs.rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if PLATE_PATTERN.search(text):
                found.append(str(path.relative_to(ROOT)))
    if found:
        return False, "placas en claro en: " + ", ".join(found)
    return True, "0 placas en claro en logs/"


def check_encryption_at_rest() -> tuple[bool, str]:
    """data/ no debe contener SQLite ni PNG en claro."""
    data = ROOT / "data"
    found: list[str] = []
    if data.exists():
        for path in data.rglob("*"):
            if not path.is_file():
                continue
            head = path.read_bytes()[:16]
            if head.startswith(b"SQLite format 3"):
                found.append(f"{path.relative_to(ROOT)} (SQLite en claro)")
            elif head.startswith(b"\x89PNG"):
                found.append(f"{path.relative_to(ROOT)} (PNG en claro)")
    if found:
        return False, "; ".join(found)
    return True, "sin SQLite ni PNG en claro en data/"


def parse_speed_factor(stdout: str) -> float | None:
    """Extrae el speed_factor de la salida de `lector process`; None si es n/d."""
    for line in stdout.splitlines():
        match = SPEED_RE.search(line)
        if match:
            if match.group(2) == "n/d":
                return None
            return float(match.group(1))
    return None


def run_pipeline(video: Path) -> tuple[float | None, int | None]:
    """Ejecuta `lector process` bajo VramMonitor y devuelve (speed_factor, pico VRAM)."""
    with VramMonitor() as monitor:
        result = subprocess.run(
            _lector_cmd("process", str(video), "--profile", PROFILE),
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        tail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "sin detalle"
        raise SystemExit(f"lector process falló (código {result.returncode}): {tail}")
    return parse_speed_factor(result.stdout), monitor.peak_mib


def _read_web_port(proc: subprocess.Popen[str]) -> int | None:
    """Lee el stdout de lector-web (máximo 30 s) y devuelve el puerto anunciado."""
    deadline = time.monotonic() + 30
    while proc.stdout is not None and time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            return None
        match = WEB_URL_RE.match(line.strip())
        if match:
            return int(match.group(1))
    return None


def _wait_port(port: int) -> bool:
    """Reintenta conectar al puerto cada 0,2 s (máximo 15 s); True si acepta."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
        except OSError:
            time.sleep(0.2)
        else:
            return True
    return False


def _web_bind_ok(port: int) -> bool:
    """Verdadero si el puerto solo escucha en 127.0.0.1 según `ss -Hltn`."""
    out = subprocess.run(
        ["ss", "-Hltn"], capture_output=True, text=True, check=False
    ).stdout.splitlines()
    loopback = any(f"127.0.0.1:{port}" in line for line in out)
    exposed = any(
        f"0.0.0.0:{port}" in line or f"*:{port}" in line or f"[::]:{port}" in line for line in out
    )
    return loopback and not exposed


def _web_status(port: int, path: str, host: str) -> int:
    """Estado HTTP de un GET a la web con la cabecera Host indicada."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path, headers={"Host": host})
        return conn.getresponse().status
    finally:
        conn.close()


def check_web_loopback() -> tuple[bool, str]:
    """Arranca lector-web --demo y comprueba loopback, Host ajeno y /api sin sesión."""
    if shutil.which("ss") is None:
        return False, "ss no disponible; omitido"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from lector_placas.web.app import main; raise SystemExit(main())",
            "--demo",
            "--no-browser",
            "--port",
            "0",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        port = _read_web_port(proc)
        if port is None:
            return False, "lector-web no arrancó"
        if not _wait_port(port):
            return False, "lector-web no acepta conexiones"
        ok_bind = _web_bind_ok(port)
        ok_host = _web_status(port, "/", f"ejemplo.invalid:{port}") == HTTP_BAD_REQUEST
        ok_auth = _web_status(port, "/api/health", f"127.0.0.1:{port}") == HTTP_UNAUTHORIZED
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    detail = (
        f"bind={'ok' if ok_bind else 'MAL'} host={'ok' if ok_host else 'MAL'} "
        f"auth={'ok' if ok_auth else 'MAL'} puerto={port}"
    )
    return ok_bind and ok_host and ok_auth, detail


def collect_checks(video: Path) -> list[tuple[str, bool, str]]:
    """Ejecuta los seis chequeos y devuelve (nombre, ok, detalle)."""
    checks: list[tuple[str, bool, str]] = []
    checks.append(("1. red bloqueada", *check_network_blocked(video)))
    checks.append(("2. permisos", *check_permissions()))
    checks.append(("3. placas en claro", *check_plates_in_logs()))
    checks.append(("4. cifrado en reposo", *check_encryption_at_rest()))

    checks.append(("7. web solo en loopback", *check_web_loopback()))

    speed, vram_peak = run_pipeline(video)
    if speed is None:
        checks.append(("5. velocidad", False, "speed_factor n/d (video sin duración)"))
    else:
        detail = f"speed_factor={speed:.2f} (>= {LIMITS['speed']})"
        checks.append(("5. velocidad", speed >= LIMITS["speed"], detail))
    if vram_peak is None:
        checks.append(("6. VRAM", False, "sin muestras de nvidia-smi"))
    else:
        detail = f"pico={vram_peak} MiB (<= {LIMITS['vram_mib']})"
        checks.append(("6. VRAM", vram_peak <= LIMITS["vram_mib"], detail))
    return checks


def main() -> int:
    """Punto de entrada: prepara el video, corre los chequeos y devuelve el código de salida."""
    parser = argparse.ArgumentParser(description="Chequeos no funcionales de nivel F")
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--regen", action="store_true", help="regenerar el video sintético")
    args = parser.parse_args()

    video = args.video
    if args.regen or not video.exists():
        generate_video(video, args.seconds)

    checks = collect_checks(video)
    failed = 0
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            failed += 1
    if failed:
        print(f"\n{failed} chequeo(s) fallaron.")
        return 1
    print("\ntodos los chequeos de nivel F pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
