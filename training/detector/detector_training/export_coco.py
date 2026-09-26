from __future__ import annotations

from pathlib import Path

from detector_training.common import (
    BASE_WEIGHTS_PATH,
    BASE_WEIGHTS_SHA256,
    check_end2end_onnx,
    publish_model,
    require_sha256,
    set_offline_env,
)


def main() -> int:
    """Exporta el detector COCO `yolo26n.pt` a ONNX end2end y lo publica.

    Returns:
        Código de salida: 0 si la exportación y verificación terminan sin error.
    """
    set_offline_env()
    from ultralytics import YOLO  # noqa: PLC0415 (offline env debe fijarse antes del import)

    require_sha256(BASE_WEIGHTS_PATH, BASE_WEIGHTS_SHA256)
    out = YOLO(str(BASE_WEIGHTS_PATH)).export(
        format="onnx", imgsz=640, nms=False, dynamic=False, simplify=True, device="cpu"
    )
    check_end2end_onnx(Path(out), 640)
    publish_model(Path(out), "yolo26n-coco")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
