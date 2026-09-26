from __future__ import annotations

import os
import urllib.request

from detector_training.common import (
    BASE_WEIGHTS_PATH,
    BASE_WEIGHTS_SHA256,
    BASE_WEIGHTS_SIZE,
    BASE_WEIGHTS_URL,
    WEIGHTS_DIR,
    TrainingError,
    sha256_file,
)

_CHUNK_SIZE = 1024 * 1024


def main() -> int:
    """Descarga `yolo26n.pt` y verifica su tamaño y SHA-256. Única etapa con red.

    Returns:
        Código de salida: 0 si el archivo queda disponible y verificado.

    Raises:
        TrainingError: si el tamaño o el SHA-256 descargados no coinciden.
    """
    if BASE_WEIGHTS_PATH.is_file() and sha256_file(BASE_WEIGHTS_PATH) == BASE_WEIGHTS_SHA256:
        print("ya descargado")
        return 0

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    part_path = WEIGHTS_DIR / "yolo26n.pt.part"
    with (
        urllib.request.urlopen(BASE_WEIGHTS_URL, timeout=60) as response,
        part_path.open("wb") as handle,
    ):
        while chunk := response.read(_CHUNK_SIZE):
            handle.write(chunk)

    size = part_path.stat().st_size
    if size != BASE_WEIGHTS_SIZE or sha256_file(part_path) != BASE_WEIGHTS_SHA256:
        part_path.unlink(missing_ok=True)
        raise TrainingError(f"hash no coincide: {part_path.name}")

    os.replace(part_path, BASE_WEIGHTS_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
