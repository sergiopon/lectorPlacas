"""Carga, escritura y CLI de la mezcla real + sintético del OCR (spec 039).

Reparte los recortes reales en train/val/test agrupando por texto de placa o
imagen de origen, añade sintéticos solo a `train` con cuota de motos y escribe
las particiones (`annotations.csv` y `groups.csv`) más un manifiesto sin textos.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ocr_training.common import DATASETS_DIR, TrainingError, validate_annotations
from ocr_training.mix_split import (
    CATEGORIES, SPLITS, Sample, category, components, origin_group, select_synthetic, split_components,
)

MANIFEST_NAME: Final[str] = "manifest.json"
GROUPS_NAME: Final[str] = "groups.csv"
TEST_VIDEO_SPLIT: Final[str] = "test_video"

_SOURCE_SPLITS: Final[tuple[str, ...]] = ("train", "val")
_DIR_MODE: Final[int] = 0o700
_FILE_MODE: Final[int] = 0o600


@dataclass(frozen=True, slots=True)
class _MixConfig:
    """Metadatos de la mezcla que se registran en el manifiesto."""

    seed: int
    val_fraction: float
    test_fraction: float
    synthetic_ratio: float
    min_moto_fraction: float
    real_sources: tuple[str, ...]
    synthetic_source: str | None
    components: int


def _require_inside_datasets(path: Path) -> Path:
    """Resuelve `path` y exige que quede dentro de `DATASETS_DIR`."""
    resolved = path.resolve()
    if DATASETS_DIR.resolve() not in resolved.parents:
        raise TrainingError(f"ruta fuera de DATASETS_DIR: {path}")
    return resolved


def _read_samples(csv_path: Path, source_name: str, source_root: Path, real: bool) -> list[Sample]:
    """Lee las filas de un `annotations.csv` y las convierte en muestras."""
    samples: list[Sample] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            image = (csv_path.parent / row["image_path"]).resolve()
            if real:
                origin = origin_group(source_name, image.relative_to(source_root).as_posix())
            else:
                origin = f"syn/{row['image_path']}"
            samples.append(Sample(image, row["plate_text"], origin, real))
    return samples


def load_real(source_dir: Path) -> list[Sample]:
    """Carga los recortes reales de un dataset anotado.

    Acepta el formato de `lector dataset export-reviewed` (`annotations.csv` en la
    raíz) o los splits `train`/`val` de un dataset de `chars_to_ocr`.
    """
    resolved = _require_inside_datasets(source_dir)
    if not resolved.is_dir():
        raise TrainingError(f"directorio inexistente: {source_dir}")
    if (resolved / MANIFEST_NAME).exists():
        raise TrainingError("no se mezcla una salida de mix_dataset")
    if (resolved / "annotations.csv").is_file():
        csv_paths = [resolved / "annotations.csv"]
    else:
        candidates = (resolved / split / "annotations.csv" for split in _SOURCE_SPLITS)
        csv_paths = [path for path in candidates if path.is_file()]
    if not csv_paths:
        raise TrainingError(f"sin annotations.csv en {resolved.name}")
    samples: list[Sample] = []
    for csv_path in csv_paths:
        validate_annotations(csv_path)
        samples.extend(_read_samples(csv_path, resolved.name, resolved, real=True))
    return samples


def load_synthetic(source_dir: Path) -> list[Sample]:
    """Carga los sintéticos del split `train`; el `val` del generador se ignora."""
    resolved = _require_inside_datasets(source_dir)
    if not resolved.is_dir():
        raise TrainingError(f"directorio inexistente: {source_dir}")
    csv_path = resolved / "train" / "annotations.csv"
    if not csv_path.is_file():
        raise TrainingError(f"sin train/annotations.csv en {resolved.name}")
    validate_annotations(csv_path)
    return _read_samples(csv_path, resolved.name, resolved, real=False)


def _validate_output(output_dir: Path, real_dirs: Sequence[Path]) -> Path:
    """Valida el destino de la mezcla y los nombres de los orígenes reales."""
    if not real_dirs:
        raise TrainingError("se requiere al menos un directorio real")
    names = [path.name for path in real_dirs]
    if len(set(names)) != len(names):
        raise TrainingError(f"nombres de origen real repetidos: {sorted(names)}")
    resolved = output_dir.resolve()
    if DATASETS_DIR.resolve() not in resolved.parents:
        raise TrainingError(f"output_dir fuera de DATASETS_DIR: {output_dir}")
    if resolved.exists():
        raise TrainingError(f"output_dir ya existe: {output_dir}")
    return resolved


def _place(sample: Sample, images_dir: Path, index: int) -> str:
    """Copia el recorte al split con un nombre generado y devuelve su ruta relativa."""
    name = f"{'real' if sample.real else 'syn'}_{index:06d}{sample.image.suffix.lower()}"
    destination = images_dir / name
    shutil.copyfile(sample.image, destination)
    os.chmod(destination, _FILE_MODE)
    return f"images/{name}"


def _write_csv(path: Path, header: tuple[str, str], rows: Sequence[tuple[str, str]]) -> None:
    """Escribe un CSV privado (0600) con terminador `\\n`."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    os.chmod(path, _FILE_MODE)


def _write_split(
    split_dir: Path, comps: Sequence[Sequence[Sample]], extras: Sequence[Sample], with_groups: bool
) -> dict[str, int]:
    """Escribe un split con sus componentes, los sintéticos extra y sus conteos."""
    split_dir.mkdir()
    os.chmod(split_dir, _DIR_MODE)
    images_dir = split_dir / "images"
    images_dir.mkdir()
    os.chmod(images_dir, _DIR_MODE)
    rows: list[tuple[str, str]] = []
    group_rows: list[tuple[str, str]] = []
    counts = {"real": 0, "synthetic": 0, "components": len(comps), **{name: 0 for name in CATEGORIES}}
    for index, comp in enumerate(comps):
        for sample in comp:
            relative = _place(sample, images_dir, len(rows))
            rows.append((relative, sample.text))
            group_rows.append((relative, f"g{index:05d}"))
            counts["real" if sample.real else "synthetic"] += 1
            counts[category(sample.text)] += 1
    for sample in extras:
        rows.append((_place(sample, images_dir, len(rows)), sample.text))
        counts["synthetic"] += 1
        counts[category(sample.text)] += 1
    _write_csv(split_dir / "annotations.csv", ("image_path", "plate_text"), rows)
    if with_groups:
        _write_csv(split_dir / GROUPS_NAME, ("image_path", "group_id"), group_rows)
    return counts


def _build_manifest(config: _MixConfig, stats: Mapping[str, Mapping[str, int]]) -> dict[str, object]:
    """Construye el manifiesto (solo conteos, tasas y nombres; sin placas)."""
    train = stats["train"]
    total = train["real"] + train["synthetic"]
    moto_fraction = train["moto"] / total
    return {
        "version": 1, "seed": config.seed, "val_fraction": config.val_fraction,
        "test_fraction": config.test_fraction, "synthetic_ratio": config.synthetic_ratio,
        "min_moto_fraction": config.min_moto_fraction, "components": config.components,
        "real_sources": list(config.real_sources), "synthetic_source": config.synthetic_source,
        "splits": {split: dict(stats[split]) for split in SPLITS},
        "train_synthetic_fraction": train["synthetic"] / total,
        "train_moto_fraction": moto_fraction,
        "moto_target_met": moto_fraction >= config.min_moto_fraction - 1e-9,
    }


def build_mix(
    output_dir: Path, real_dirs: Sequence[Path], synthetic_dir: Path | None, val_fraction: float,
    test_fraction: float, synthetic_ratio: float, min_moto_fraction: float, seed: int,
    frozen_dir: Path | None = None,
) -> dict[str, object]:
    """Construye el dataset mezclado de recortes reales y sintéticos.

    Reparte los reales por componente, selecciona los sintéticos para `train`
    según la cuota y escribe las particiones y el manifiesto. Si la escritura
    falla, borra la salida parcial y relanza el error. Con `frozen_dir` hereda el
    test congelado de esa mezcla y añade `test_video` (spec 054).
    """
    if frozen_dir is not None:
        # Import diferido: `mix_frozen` importa de este módulo (evita el ciclo).
        from ocr_training.mix_frozen import build_frozen_mix

        return build_frozen_mix(
            output_dir, frozen_dir, real_dirs, synthetic_dir, val_fraction, test_fraction,
            synthetic_ratio, min_moto_fraction, seed,
        )
    resolved = _validate_output(output_dir, real_dirs)
    real: list[Sample] = []
    for source_dir in real_dirs:
        real.extend(load_real(source_dir))
    comps = components(real)
    parts = split_components(comps, val_fraction, test_fraction, seed)
    real_train = [sample for comp in parts["train"] for sample in comp]
    excluded = {s.text for split in ("val", "test") for comp in parts[split] for s in comp}
    if synthetic_dir is None:
        chosen: list[Sample] = []
    else:
        chosen = select_synthetic(
            load_synthetic(synthetic_dir), real_train, excluded, synthetic_ratio,
            min_moto_fraction, seed,
        )
    config = _MixConfig(
        seed=seed, val_fraction=val_fraction, test_fraction=test_fraction,
        synthetic_ratio=synthetic_ratio, min_moto_fraction=min_moto_fraction,
        real_sources=tuple(path.name for path in real_dirs),
        synthetic_source=None if synthetic_dir is None else synthetic_dir.name,
        components=len(comps),
    )
    try:
        resolved.mkdir(parents=True)
        os.chmod(resolved, _DIR_MODE)
        stats = {
            split: _write_split(
                resolved / split, parts[split], chosen if split == "train" else (),
                with_groups=split != "train",
            )
            for split in SPLITS
        }
        manifest = _build_manifest(config, stats)
        with (resolved / MANIFEST_NAME).open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(manifest, indent=2, sort_keys=True))
        os.chmod(resolved / MANIFEST_NAME, _FILE_MODE)
        for split in SPLITS:
            validate_annotations(resolved / split / "annotations.csv")
    except Exception:
        shutil.rmtree(resolved, ignore_errors=True)
        raise
    return manifest


def build_parser() -> argparse.ArgumentParser:
    """Construye el parser de la CLI de la mezcla."""
    parser = argparse.ArgumentParser(
        description="Mezcla recortes reales y sintéticos de placas para el OCR."
    )
    parser.add_argument("--real", type=Path, action="append", required=True)
    parser.add_argument("--synthetic", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-from", type=Path, default=None)
    parser.add_argument("--val-fraction", type=float, default=0.10)
    parser.add_argument("--test-fraction", type=float, default=0.20)
    parser.add_argument("--synthetic-ratio", type=float, default=1.0)
    parser.add_argument("--min-moto-fraction", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Construye la mezcla desde la línea de comandos (nunca imprime placas)."""
    args = build_parser().parse_args(argv)
    synthetic = None if args.synthetic is None else DATASETS_DIR / args.synthetic
    frozen = None if args.frozen_from is None else DATASETS_DIR / args.frozen_from
    manifest = build_mix(
        DATASETS_DIR / args.output, [DATASETS_DIR / path for path in args.real], synthetic,
        args.val_fraction, args.test_fraction, args.synthetic_ratio, args.min_moto_fraction,
        args.seed, frozen,
    )
    splits = cast("dict[str, dict[str, int]]", manifest["splits"])
    order = (*SPLITS, TEST_VIDEO_SPLIT) if TEST_VIDEO_SPLIT in splits else SPLITS
    for split in order:
        stats = splits[split]
        print(
            f"{split}: real={stats['real']} synthetic={stats['synthetic']} "
            f"moto={stats['moto']} components={stats['components']}"
        )
    print(
        f"train_synthetic_fraction={cast(float, manifest['train_synthetic_fraction']):.3f} "
        f"train_moto_fraction={cast(float, manifest['train_moto_fraction']):.3f} "
        f"moto_target_met={manifest['moto_target_met']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
