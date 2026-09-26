from __future__ import annotations

import os
import urllib.request

from ocr_training.common import ASSETS, BASE_URL, WEIGHTS_DIR, TrainingError, sha256_file

_CHUNK_SIZE = 1024 * 1024


def main() -> int:
    """Descarga los pesos y configuraciones de `ASSETS`. Única etapa con red.

    Returns:
        Código de salida: 0 si todos los recursos quedan disponibles y verificados.

    Raises:
        TrainingError: si el tamaño o el SHA-256 descargados no coinciden.
    """
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    for name, (expected_sha256, expected_size) in ASSETS.items():
        path = WEIGHTS_DIR / name
        if (
            path.is_file()
            and path.stat().st_size == expected_size
            and sha256_file(path) == expected_sha256
        ):
            print(f"ya descargado: {name}")
            continue

        part_path = WEIGHTS_DIR / f"{name}.part"
        url = f"{BASE_URL}/{name}"
        with (
            urllib.request.urlopen(url, timeout=60) as response,
            part_path.open("wb") as handle,
        ):
            while chunk := response.read(_CHUNK_SIZE):
                handle.write(chunk)

        size = part_path.stat().st_size
        if size != expected_size or sha256_file(part_path) != expected_sha256:
            part_path.unlink(missing_ok=True)
            raise TrainingError(f"hash no coincide: {name}")

        os.replace(part_path, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
