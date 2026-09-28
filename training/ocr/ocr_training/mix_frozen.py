"""Mezcla congelada: hereda el test de una mezcla previa y añade `test_video` (spec 054).

Carga una salida de `mix_dataset` (el test congelado de ADR-014), ancla los
componentes nuevos cuyos textos ya vieron los splits congelados y escribe cuatro
splits: `test` se copia byte a byte, `test_video` reúne el dominio nuevo y
`train`/`val` heredan sus filas reales.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from ocr_training.common import TrainingError, validate_annotations
from ocr_training.mix_dataset import (
    GROUPS_NAME, MANIFEST_NAME, TEST_VIDEO_SPLIT, _DIR_MODE, _FILE_MODE, _place,
    _require_inside_datasets, _validate_output, _write_csv, load_real, load_synthetic,
)
from ocr_training.mix_split import (
    CATEGORIES, SPLITS, Sample, category, components, select_synthetic, split_components,
)

_ANCHOR_ORDER: Final[tuple[str, ...]] = ("test", "val", "train")
_MIX_SPLITS: Final[tuple[str, ...]] = (*SPLITS, TEST_VIDEO_SPLIT)
_OUTPUT_SPLIT_OF: Final[Mapping[str, str]] = {"train": "train", "val": "val", "test": TEST_VIDEO_SPLIT}


@dataclass(frozen=True, slots=True)
class FrozenRow:
    """Fila real de un split congelado, con su `group_id` (en `train`, por texto)."""

    image: Path
    text: str
    group_id: str | None


@dataclass(frozen=True, slots=True)
class FrozenMix:
    """Filas reales por split congelado y nombres de sus fuentes reales."""

    name: str
    real_sources: tuple[str, ...]
    train: tuple[FrozenRow, ...]
    val: tuple[FrozenRow, ...]
    test: tuple[FrozenRow, ...]

    def rows(self, split: str) -> tuple[FrozenRow, ...]:
        """Filas congeladas de `train`, `val` o `test`."""
        return {"train": self.train, "val": self.val, "test": self.test}[split]

    def text_splits(self) -> dict[str, str]:
        """Mapa de texto congelado a su split (único, validado al cargar)."""
        return {row.text: split for split in SPLITS for row in self.rows(split)}


def _read_frozen_rows(mix_dir: Path, split: str) -> list[FrozenRow]:
    """Filas reales de un split congelado, con su grupo (el `train`, por texto)."""
    split_dir = mix_dir / split
    csv_path = split_dir / "annotations.csv"
    if not csv_path.is_file():
        raise TrainingError(f"sin annotations.csv en el split {split}")
    validate_annotations(csv_path)
    groups: dict[str, str] = {}
    if split != "train":
        if not (split_dir / GROUPS_NAME).is_file():
            raise TrainingError(f"sin groups.csv en el split {split}")
        with (split_dir / GROUPS_NAME).open(newline="", encoding="utf-8") as handle:
            groups = {row["image_path"]: row["group_id"] for row in csv.DictReader(handle)}
    rows: list[FrozenRow] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            image_path = row["image_path"]
            if not PurePosixPath(image_path).name.startswith("real_"):
                continue
            if split != "train" and image_path not in groups:
                raise TrainingError(f"grupo ausente para {image_path}")
            rows.append(FrozenRow((split_dir / image_path).resolve(), row["plate_text"], groups.get(image_path)))
    if split != "train":
        return rows
    numbers = {text: f"g{index:05d}" for index, text in enumerate(dict.fromkeys(row.text for row in rows))}
    return [FrozenRow(row.image, row.text, numbers[row.text]) for row in rows]


def load_frozen(mix_dir: Path) -> FrozenMix:
    """Carga una salida de `mix_dataset` como mezcla congelada.

    Raises:
        TrainingError: si la ruta no es una mezcla válida dentro de `DATASETS_DIR`,
            le falta un split o un mismo texto aparece en dos splits.
    """
    resolved = _require_inside_datasets(mix_dir)
    if not resolved.is_dir():
        raise TrainingError(f"directorio inexistente: {mix_dir}")
    manifest_path = resolved / MANIFEST_NAME
    if not manifest_path.is_file():
        raise TrainingError(f"sin {MANIFEST_NAME}: no es una mezcla: {mix_dir}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TrainingError(f"manifiesto inválido: {manifest_path.name}") from exc
    sources = manifest.get("real_sources")
    if not isinstance(sources, list):
        raise TrainingError("manifiesto sin real_sources")
    frozen = FrozenMix(
        name=resolved.name, real_sources=tuple(str(source) for source in sources),
        train=tuple(_read_frozen_rows(resolved, "train")),
        val=tuple(_read_frozen_rows(resolved, "val")),
        test=tuple(_read_frozen_rows(resolved, "test")),
    )
    seen: dict[str, str] = {}
    for split in SPLITS:
        for row in frozen.rows(split):
            if seen.setdefault(row.text, split) != split:
                raise TrainingError("mezcla congelada inconsistente")
    return frozen


def _anchor_split(comp: Sequence[Sample], text_split: Mapping[str, str]) -> str | None:
    """Split congelado más restrictivo con un texto del componente."""
    texts = {text_split.get(sample.text) for sample in comp}
    return next((split for split in _ANCHOR_ORDER if split in texts), None)


def assign_new_components(
    comps: Sequence[Sequence[Sample]], frozen: FrozenMix, val_fraction: float,
    test_fraction: float, seed: int,
) -> dict[str, list[list[Sample]]]:
    """Reparte los componentes nuevos: anclados por texto y libres por sorteo.

    Los anclados van al split congelado más restrictivo en que aparezca su texto
    (`test` > `val` > `train`); los de `test` van a `test_video`, nunca a `test`.
    Los libres se reparten con `split_components` y su parte `test` va a `test_video`.

    Raises:
        TrainingError: si `split_components` no puede repartir los libres.
    """
    text_split = frozen.text_splits()
    parts: dict[str, list[list[Sample]]] = {split: [] for split in _MIX_SPLITS}
    free: list[list[Sample]] = []
    for comp in comps:
        target = _anchor_split(comp, text_split)
        if target is None:
            free.append(list(comp))
        else:
            parts[_OUTPUT_SPLIT_OF[target]].append(list(comp))
    if not free:
        return parts
    split_parts = split_components(free, val_fraction, test_fraction, seed)
    parts["train"] += split_parts["train"]
    parts["val"] += split_parts["val"]
    parts[TEST_VIDEO_SPLIT] += split_parts["test"]
    return parts


def _frozen_samples(rows: Sequence[FrozenRow]) -> list[Sample]:
    """Muestras reales de las filas congeladas (origen por imagen)."""
    return [Sample(row.image, row.text, row.image.as_posix(), True) for row in rows]


def _split_rows(
    frozen: Sequence[FrozenRow], comps: Sequence[Sequence[Sample]], start: int,
    extras: Sequence[Sample] = (),
) -> list[tuple[Sample, str | None]]:
    """Filas de un split: congeladas (con su grupo), componentes nuevos y extras."""
    rows = [(sample, row.group_id) for row, sample in zip(frozen, _frozen_samples(frozen), strict=True)]
    rows += [(sample, f"g{index:05d}") for index, comp in enumerate(comps, start=start) for sample in comp]
    return rows + [(sample, None) for sample in extras]


def _write_split(
    split_dir: Path, rows: Sequence[tuple[Sample, str | None]], with_groups: bool
) -> dict[str, int]:
    """Escribe un split con `_place` (los extras no cuentan como componentes)."""
    images_dir = split_dir / "images"
    for directory in (split_dir, images_dir):
        directory.mkdir()
        os.chmod(directory, _DIR_MODE)
    counts = {"real": 0, "synthetic": 0, "components": len({group for _, group in rows if group is not None}),
              **{name: 0 for name in CATEGORIES}}
    csv_rows: list[tuple[str, str]] = []
    groups: list[tuple[str, str]] = []
    for sample, group_id in rows:
        relative = _place(sample, images_dir, len(csv_rows))
        csv_rows.append((relative, sample.text))
        if group_id is not None:
            groups.append((relative, group_id))
        counts["real" if sample.real else "synthetic"] += 1
        counts[category(sample.text)] += 1
    _write_csv(split_dir / "annotations.csv", ("image_path", "plate_text"), csv_rows)
    if with_groups:
        _write_csv(split_dir / GROUPS_NAME, ("image_path", "group_id"), groups)
    return counts


def _next_group(rows: Sequence[FrozenRow]) -> int:
    """Número de grupo que continúa la numeración congelada."""
    numbers = [int(row.group_id[1:]) for row in rows if row.group_id is not None]
    return max(numbers) + 1 if numbers else 0


def _copy_frozen_test(source: Path, destination: Path) -> dict[str, int]:
    """Copia el `test` congelado byte a byte y cuenta sus filas."""
    shutil.copytree(source, destination)
    for path in (destination, destination / "images", *(destination / "images").iterdir()):
        os.chmod(path, _DIR_MODE if path.is_dir() else _FILE_MODE)
    for name in ("annotations.csv", GROUPS_NAME):
        os.chmod(destination / name, _FILE_MODE)
    with (destination / "annotations.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    with (destination / GROUPS_NAME).open(newline="", encoding="utf-8") as handle:
        groups = list(csv.DictReader(handle))
    counts = {"real": 0, "synthetic": 0, "components": len({row["group_id"] for row in groups}),
              **{name: 0 for name in CATEGORIES}}
    for row in rows:
        counts["synthetic" if PurePosixPath(row["image_path"]).name.startswith("syn_") else "real"] += 1
        counts[category(row["plate_text"])] += 1
    return counts


def _manifest(
    frozen: FrozenMix, real_dirs: Sequence[Path], synthetic_dir: Path | None, seed: int,
    val_fraction: float, test_fraction: float, synthetic_ratio: float, min_moto_fraction: float,
    stats: Mapping[str, Mapping[str, int]],
) -> dict[str, object]:
    """Manifiesto versión 2: conteos, tasas y nombres; nunca textos de placa."""
    train = stats["train"]
    total = train["real"] + train["synthetic"]
    moto_fraction = train["moto"] / total
    return {
        "version": 2, "frozen_from": frozen.name, "seed": seed, "val_fraction": val_fraction,
        "test_fraction": test_fraction, "synthetic_ratio": synthetic_ratio,
        "min_moto_fraction": min_moto_fraction,
        "synthetic_source": None if synthetic_dir is None else synthetic_dir.name,
        "components": sum(stats[split]["components"] for split in _MIX_SPLITS),
        "real_sources": [path.name for path in real_dirs],
        "splits": {split: dict(stats[split]) for split in _MIX_SPLITS},
        "train_synthetic_fraction": train["synthetic"] / total, "train_moto_fraction": moto_fraction,
        "moto_target_met": moto_fraction >= min_moto_fraction - 1e-9,
    }


def build_frozen_mix(
    output_dir: Path, frozen_dir: Path, real_dirs: Sequence[Path], synthetic_dir: Path | None,
    val_fraction: float, test_fraction: float, synthetic_ratio: float, min_moto_fraction: float,
    seed: int,
) -> dict[str, object]:
    """Mezcla que hereda el test congelado y añade `test_video` (spec 054).

    Reparte los componentes de las fuentes nuevas, escribe los cuatro splits y el
    manifiesto. Si algo falla, borra la salida parcial y relanza el error.
    """
    resolved = _validate_output(output_dir, real_dirs)
    frozen = load_frozen(frozen_dir)
    for source_dir in real_dirs:
        if source_dir.name in frozen.real_sources:
            raise TrainingError(f"fuente ya incluida en la mezcla congelada: {source_dir.name}")
    new = [sample for source_dir in real_dirs for sample in load_real(source_dir)]
    parts = assign_new_components(components(new), frozen, val_fraction, test_fraction, seed)
    real_train = _frozen_samples(frozen.train) + [s for comp in parts["train"] for s in comp]
    excluded = {row.text for row in (*frozen.val, *frozen.test)} | {
        sample.text for split in ("val", TEST_VIDEO_SPLIT) for comp in parts[split] for sample in comp
    }
    chosen = [] if synthetic_dir is None else select_synthetic(
        load_synthetic(synthetic_dir), real_train, excluded, synthetic_ratio, min_moto_fraction, seed,
    )
    frozen_path = _require_inside_datasets(frozen_dir)
    try:
        resolved.mkdir(parents=True)
        os.chmod(resolved, _DIR_MODE)
        train_rows = _split_rows(frozen.train, parts["train"], _next_group(frozen.train), chosen)
        stats = {
            "train": _write_split(resolved / "train", train_rows, False),
            "val": _write_split(
                resolved / "val", _split_rows(frozen.val, parts["val"], _next_group(frozen.val)), True
            ),
            "test": _copy_frozen_test(frozen_path / "test", resolved / "test"),
            TEST_VIDEO_SPLIT: _write_split(
                resolved / TEST_VIDEO_SPLIT, _split_rows((), parts[TEST_VIDEO_SPLIT], 0), True
            ),
        }
        manifest = _manifest(frozen, real_dirs, synthetic_dir, seed, val_fraction, test_fraction,
                             synthetic_ratio, min_moto_fraction, stats)
        with (resolved / MANIFEST_NAME).open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(manifest, indent=2, sort_keys=True))
        os.chmod(resolved / MANIFEST_NAME, _FILE_MODE)
        for split in _MIX_SPLITS:
            validate_annotations(resolved / split / "annotations.csv")
    except Exception:
        shutil.rmtree(resolved, ignore_errors=True)
        raise
    return manifest
