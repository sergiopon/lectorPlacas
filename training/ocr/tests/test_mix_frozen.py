from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
import pytest

from ocr_training import mix_dataset as md
from ocr_training import mix_frozen as mf
from ocr_training.common import TrainingError

FROZEN = "frozen"
OUT = "mix_v2"
VIDEO = "test_video"


def write_split(split_dir: Path, rows: Sequence[tuple[str, str]]) -> None:
    """Escribe un split con imágenes sintéticas distintas por (archivo, texto)."""
    images = split_dir / "images"
    images.mkdir(parents=True, exist_ok=True)
    for name, text in rows:
        digest = np.frombuffer(hashlib.sha256(f"{name}:{text}".encode()).digest()[:3], np.uint8)
        assert cv2.imwrite(str(images / name), np.full((20, 40, 3), digest, np.uint8))
    with (split_dir / "annotations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("image_path", "plate_text"))
        writer.writerows((f"images/{name}", text) for name, text in rows)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def snapshot(mix: Path) -> dict[str, bytes]:
    """Archivos de la mezcla por ruta relativa, para comparar byte a byte."""
    return {
        path.relative_to(mix).as_posix(): path.read_bytes()
        for path in sorted(mix.rglob("*"))
        if path.is_file()
    }


def texts_of(mix: Path, split: str) -> list[str]:
    return [row["plate_text"] for row in read_rows(mix / split / "annotations.csv")]


def real_texts(mix: Path, split: str) -> list[str]:
    return [
        row["plate_text"]
        for row in read_rows(mix / split / "annotations.csv")
        if Path(row["image_path"]).name.startswith("real_")
    ]


def synthetic_texts(mix: Path, split: str) -> list[str]:
    return [
        row["plate_text"]
        for row in read_rows(mix / split / "annotations.csv")
        if Path(row["image_path"]).name.startswith("syn_")
    ]


def images_of(mix: Path, split: str) -> dict[str, set[bytes]]:
    """Bytes de las imágenes por texto: compara contenido, no nombres."""
    result: dict[str, set[bytes]] = {}
    for row in read_rows(mix / split / "annotations.csv"):
        result.setdefault(row["plate_text"], set()).add((mix / split / row["image_path"]).read_bytes())
    return result


def rf(group: int, index: int = 0) -> str:
    return f"src__{group:04d}_jpg.rf.ab12cd_{index}.png"


def real_source(root: Path) -> Path:
    """Dataset real base de la mezcla congelada (30 componentes: 26 otros, 4 motos)."""
    source = root / "real1"
    texts = [f"CAR{i:03d}" for i in range(26)] + [f"MOT{i:02d}A" for i in range(4)]
    rows = [(rf(i), text) for i, text in enumerate(texts)]
    write_split(source / "train", [*rows[:25], (rf(1, 1), "CAR900")])
    write_split(source / "val", [*rows[25:], (rf(100), "CAR000")])
    return source


def synthetic_source(root: Path, extra: Sequence[str] = ()) -> Path:
    source = root / "syn"
    names = iter(f"syn_{i:06d}.png" for i in range(1000))
    rows = [(next(names), f"SYM{i:02d}A") for i in range(60)]
    rows += [(next(names), f"{i:03d}SYN") for i in range(60)]
    rows += [(next(names), f"SYN{i:03d}") for i in range(60)]
    rows += [(next(names), text) for text in extra]
    write_split(source / "train", rows)
    write_split(source / "val", [("val_000000.png", "ZZZ999")])
    return source


def own_source(root: Path, texts: Sequence[str], name: str = "own") -> Path:
    source = root / name
    write_split(source / "train", [(f"{i:06d}.png", text) for i, text in enumerate(texts)])
    return source


def make_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Construye la mezcla congelada con `build_mix`, sin `frozen_dir`."""
    monkeypatch.setattr(md, "DATASETS_DIR", tmp_path)
    real_source(tmp_path)
    synthetic_source(tmp_path)
    md.build_mix(tmp_path / FROZEN, [tmp_path / "real1"], tmp_path / "syn", 0.1, 0.2, 1.0, 0.2, 0)
    return tmp_path / FROZEN


def new_texts(count: int = 10) -> list[str]:
    return [f"OWN{i:03d}" for i in range(count)]


def test_frozen_test_is_copied_byte_for_byte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = make_frozen(tmp_path, monkeypatch)
    own_source(tmp_path, new_texts())
    md.build_mix(tmp_path / OUT, [tmp_path / "own"], None, 0.1, 0.2, 1.0, 0.2, 0, frozen)
    assert snapshot(tmp_path / OUT / "test") == snapshot(frozen / "test")


def test_frozen_rows_keep_their_split(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = make_frozen(tmp_path, monkeypatch)
    own_source(tmp_path, new_texts())
    md.build_mix(tmp_path / OUT, [tmp_path / "own"], None, 0.1, 0.2, 1.0, 0.2, 0, frozen)
    for split in ("train", "val"):
        output = images_of(tmp_path / OUT, split)
        for row in read_rows(frozen / split / "annotations.csv"):
            if not Path(row["image_path"]).name.startswith("real_"):
                continue
            assert (frozen / split / row["image_path"]).read_bytes() in output[row["plate_text"]]


def test_new_sample_sharing_test_text_goes_to_test_video(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = make_frozen(tmp_path, monkeypatch)
    shared = texts_of(frozen, "test")[0]
    own_source(tmp_path, [shared, *new_texts()])
    md.build_mix(tmp_path / OUT, [tmp_path / "own"], None, 0.1, 0.2, 1.0, 0.2, 0, frozen)
    new_image = (tmp_path / "own" / "train" / "images" / "000000.png").read_bytes()
    assert new_image in images_of(tmp_path / OUT, VIDEO)[shared]
    assert shared not in texts_of(tmp_path / OUT, "train")
    assert shared not in texts_of(tmp_path / OUT, "val")


def test_anchor_precedence_is_test_then_val_then_train(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = make_frozen(tmp_path, monkeypatch)
    val_text = texts_of(frozen, "val")[0]
    train_text = real_texts(frozen, "train")[0]
    source = tmp_path / "own"
    linked = [("000000.png", val_text), ("000000.png", train_text)]
    write_split(source / "train", [*linked, *[(f"{i + 1:06d}.png", text) for i, text in enumerate(new_texts())]])
    md.build_mix(tmp_path / OUT, [source], None, 0.1, 0.2, 1.0, 0.2, 0, frozen)
    shared_image = (source / "train" / "images" / "000000.png").read_bytes()
    val_images = images_of(tmp_path / OUT, "val")
    assert shared_image in val_images[val_text] and shared_image in val_images[train_text]
    assert shared_image not in {image for images in images_of(tmp_path / OUT, "train").values() for image in images}
    assert shared_image not in {image for images in images_of(tmp_path / OUT, VIDEO).values() for image in images}


def test_free_components_split_with_test_to_test_video(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = make_frozen(tmp_path, monkeypatch)
    own_source(tmp_path, new_texts())
    md.build_mix(tmp_path / OUT, [tmp_path / "own"], None, 0.1, 0.2, 1.0, 0.2, 0, frozen)
    frozen_texts = {text for split in ("train", "val", "test") for text in texts_of(frozen, split)}
    for split in ("train", "val", VIDEO):
        assert set(texts_of(tmp_path / OUT, split)) - frozen_texts
    assert snapshot(tmp_path / OUT / "test") == snapshot(frozen / "test")


def test_synthetics_exclude_eval_texts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = make_frozen(tmp_path, monkeypatch)
    eval_texts = {texts_of(frozen, "val")[0], texts_of(frozen, "test")[0]}
    synthetic_source(tmp_path, extra=sorted(eval_texts))
    own_source(tmp_path, new_texts())
    md.build_mix(tmp_path / OUT, [tmp_path / "own"], tmp_path / "syn", 0.1, 0.2, 1.0, 0.2, 0, frozen)
    chosen = synthetic_texts(tmp_path / OUT, "train")
    assert chosen and not set(chosen) & eval_texts
    assert not set(texts_of(tmp_path / OUT, "train")) & eval_texts


def test_repeated_source_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = make_frozen(tmp_path, monkeypatch)
    with pytest.raises(TrainingError, match="mezcla congelada"):
        md.build_mix(tmp_path / OUT, [tmp_path / "real1"], None, 0.1, 0.2, 1.0, 0.2, 0, frozen)
    assert not (tmp_path / OUT).exists()


def test_invalid_frozen_dir_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_frozen(tmp_path, monkeypatch)
    own = own_source(tmp_path, new_texts())
    empty = tmp_path / "notmix"
    empty.mkdir()
    with pytest.raises(TrainingError):
        md.build_mix(tmp_path / OUT, [own], None, 0.1, 0.2, 1.0, 0.2, 0, empty)
    splitless = tmp_path / "sin_splits"
    splitless.mkdir()
    (splitless / "manifest.json").write_text('{"real_sources": ["real1"]}', encoding="utf-8")
    with pytest.raises(TrainingError):
        mf.load_frozen(splitless)
    assert not (tmp_path / OUT).exists()


def test_manifest_version_2_without_plate_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = make_frozen(tmp_path, monkeypatch)
    own_source(tmp_path, new_texts())
    manifest = md.build_mix(tmp_path / OUT, [tmp_path / "own"], tmp_path / "syn", 0.1, 0.2, 1.0, 0.2, 0, frozen)
    assert manifest["version"] == 2
    assert manifest["frozen_from"] == FROZEN
    assert set(manifest["splits"]) == {"train", "val", "test", VIDEO}
    assert manifest["real_sources"] == ["own"]
    assert json.loads((tmp_path / OUT / "manifest.json").read_text(encoding="utf-8")) == manifest
    dumped = json.dumps(manifest)
    used = {text for split in ("train", "val", "test") for text in texts_of(frozen, split)}
    used |= set(new_texts()) | set(synthetic_texts(tmp_path / OUT, "train"))
    assert used and all(text not in dumped for text in used)


def test_frozen_mix_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = make_frozen(tmp_path, monkeypatch)
    own_source(tmp_path, new_texts())
    for name in ("a", "b"):
        md.build_mix(tmp_path / name, [tmp_path / "own"], tmp_path / "syn", 0.1, 0.2, 1.0, 0.2, 0, frozen)
    assert snapshot(tmp_path / "a") == snapshot(tmp_path / "b")


def test_main_prints_test_video_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    make_frozen(tmp_path, monkeypatch)
    own_source(tmp_path, new_texts())
    assert md.main(["--real", "own", "--frozen-from", FROZEN, "--output", OUT]) == 0
    printed = capsys.readouterr().out
    assert f"{VIDEO}:" in printed and "train:" in printed and "test:" in printed
    for text in new_texts() + synthetic_texts(tmp_path / OUT, "train"):
        assert text not in printed
