"""Verifica que la GPU NVIDIA y el proveedor CUDA de onnxruntime estén disponibles."""

from __future__ import annotations

import subprocess

import onnxruntime


def main() -> int:
    """Ejecuta las verificaciones de GPU y proveedor CUDA.

    Returns:
        int: 0 si la GPU es compute_cap 12.0 y CUDAExecutionProvider está disponible;
        1 en otro caso.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,compute_cap", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("nvidia-smi no encontrado")
        return 1

    output = result.stdout.strip()
    name, _, compute_cap = output.partition(", ")

    onnxruntime.preload_dlls(directory="")
    providers = onnxruntime.get_available_providers()

    print(f"gpu={name} compute_cap={compute_cap}")
    print(f"providers={providers}")

    if compute_cap == "12.0" and "CUDAExecutionProvider" in providers:
        return 0

    print(f"causa: compute_cap={compute_cap} providers={providers}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
