from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
import pytest

from ocr_training import mix_dataset as md
from ocr_training import mix_split as ms
from ocr_training.common import TrainingError, validate_annotations


def sample(text: str, origin: str, real: bool = True) -> ms.Sample:
    return ms.Sample(Path(f"/x/{origin}_{text}.png"), text, origin, real)


def write_split(split_dir: Path, rows: Sequence[tuple[str, str]]) -> None:
    (split_dir / "images").mkdir(parents=True, exist_ok=True)
    for name, _ in rows:
        assert cv2.imwrite(str(split_dir / "images" / name), np.full((20, 40, 3), 100, np.uint8))
    with (split_dir / "annotations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("image_path", "plate_text"))
        writer.writerows((f"images/{name}", text) for name, text in rows)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def rf(group: int, index: int = 0) -> str:
    return f"src__{group:04d}_jpg.rf.ab12cd_{index}.png"


def real_source(root: Path) -> Path:
    source = root / "real1"
    texts = [f"CAR{i:03d}" for i in range(26)] + [f"MOT{i:02d}A" for i in range(4)]
    rows = [(rf(i), text) for i, text in enumerate(texts)]
    write_split(source / "train", [*rows[:25], (rf(1, 1), "CAR900")])
    write_split(source / "val", [*rows[25:], (rf(100), "CAR000")])
    return source


def synthetic_source(root: Path) -> Path:
    source = root / "syn"
    names = iter(f"syn_{i:06d}.png" for i in range(1000))
    rows = [(next(names), f"SYM{i:02d}A") for i in range(60)]
    rows += [(next(names), f"{i:03d}SYN") for i in range(60)]
    rows += [(next(names), f"SYN{i:03d}") for i in range(60)]
    write_split(source / "train", rows)
    write_split(source / "val", [("val_000000.png", "ZZZ999")])
    return source


@pytest.mark.parametrize(("text", "expected"), [
    ("ABC123", "other"), ("ABC12D", "moto"), ("ABC12", "moto"), ("123ABC", "motocarro"), ("R12345", "other"),
])
def test_category(text: str, expected: str) -> None:
    assert ms.category(text) == expected


def test_origin_group() -> None:
    name = "train/images/ocr_placas_colombia__0069_jpg.rf.fe61_6.png"
    assert ms.origin_group("ocr_colombia", name) == "ocr_colombia/ocr_placas_colombia/0069_jpg"
    assert ms.origin_group("own", "images/000001.png") == "own/images/000001.png"


def test_components_link_text_and_origin() -> None:
    a, b = sample("AAA111", "o1"), sample("AAA111", "o2")
    c, d = sample("BBB222", "o2"), sample("CCC333", "o3")
    result = ms.components([d, a, b, c])
    assert [[s.text for s in comp] for comp in result] == [["CCC333"], ["AAA111", "AAA111", "BBB222"]]


def test_split_components_is_stratified_and_deterministic() -> None:
    comps = [[sample(f"AAA{i:03d}", f"o{i}")] for i in range(40)]
    comps += [[sample(f"MOT{i:02d}A", f"m{i}")] for i in range(10)]
    result = ms.split_components(comps, 0.1, 0.2, 0)
    assert [len(result[s]) for s in ms.SPLITS] == [35, 5, 10]
    moto = {s: sum(ms.component_category(c) == "moto" for c in result[s]) for s in ms.SPLITS}
    assert moto == {"train": 7, "val": 1, "test": 2}
    assert ms.split_components(comps, 0.1, 0.2, 0) == result
    assert ms.split_components(comps, 0.1, 0.2, 1)["test"] != result["test"]
    origins = [{c[0].origin for c in result[s]} for s in ms.SPLITS]
    assert sum(len(o) for o in origins) == 50 and len(set().union(*origins)) == 50


@pytest.mark.parametrize(("val", "test"), [(0.0, 0.2), (0.1, 0.0), (0.5, 0.5)])
def test_split_components_invalid_fractions(val: float, test: float) -> None:
    with pytest.raises(TrainingError):
        ms.split_components([[sample("AAA000", "o0")]], val, test, 0)


def test_split_components_empty_partition() -> None:
    with pytest.raises(TrainingError):
        ms.split_components([[sample("AAA000", "o0")], [sample("AAA001", "o1")]], 0.1, 0.2, 0)


def real_train() -> list[ms.Sample]:
    return [sample(f"AAA{i:03d}", f"r{i}") for i in range(76)] + [sample(f"MOT{i:02d}A", f"q{i}") for i in range(4)]


def synthetic_pool(others: int = 100) -> list[ms.Sample]:
    pool = [sample(f"SYM{i:02d}A", f"s{i}", False) for i in range(100)]
    pool += [sample(f"{i:03d}SYN", f"t{i}", False) for i in range(100)]
    return pool + [sample(f"SYN{i:03d}", f"u{i}", False) for i in range(others)]


def test_select_synthetic_quota() -> None:
    chosen = ms.select_synthetic(synthetic_pool(), real_train(), frozenset(), 1.0, 0.2, 0)
    assert Counter(ms.category(s.text) for s in chosen) == Counter({"other": 44, "moto": 28, "motocarro": 8})
    assert all(not s.real for s in chosen)
    assert ms.select_synthetic(synthetic_pool(), real_train(), frozenset(), 1.0, 0.2, 0) == chosen
    half = ms.select_synthetic(synthetic_pool(), real_train(), frozenset(), 0.5, 0.2, 0)
    assert Counter(ms.category(s.text) for s in half) == Counter({"other": 17, "moto": 20, "motocarro": 3})
    assert ms.select_synthetic(synthetic_pool(), real_train(), frozenset(), 0.0, 0.2, 0) == []


def test_select_synthetic_excludes_eval_texts() -> None:
    chosen = ms.select_synthetic(synthetic_pool(others=45), real_train(), frozenset({"SYN000"}), 1.0, 0.2, 0)
    others = {s.text for s in chosen if ms.category(s.text) == "other"}
    assert len(others) == 44 and "SYN000" not in others


@pytest.mark.parametrize(("ratio", "moto"), [(1.5, 0.2), (-0.1, 0.2), (1.0, 1.0)])
def test_select_synthetic_invalid(ratio: float, moto: float) -> None:
    with pytest.raises(TrainingError):
        ms.select_synthetic(synthetic_pool(), real_train(), frozenset(), ratio, moto, 0)


def test_select_synthetic_shortage() -> None:
    pool = [sample(f"SYM{i:02d}A", f"s{i}", False) for i in range(5)] + synthetic_pool()[100:]
    with pytest.raises(TrainingError):
        ms.select_synthetic(pool, real_train(), frozenset(), 1.0, 0.2, 0)


def test_load_real_reviewed_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(md, "DATASETS_DIR", tmp_path)
    write_split(tmp_path / "own", [("000000.png", "OWN001"), ("000001.png", "OWN001")])
    samples = md.load_real(tmp_path / "own")
    assert [s.origin for s in samples] == ["own/images/000000.png", "own/images/000001.png"]
    assert all(s.real and s.image.is_file() for s in samples)
    assert len(ms.components(samples)) == 1


def test_build_mix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(md, "DATASETS_DIR", tmp_path)
    real, syn, out = real_source(tmp_path), synthetic_source(tmp_path), tmp_path / "mix"
    manifest = md.build_mix(out, [real], syn, 0.1, 0.2, 1.0, 0.2, 0)
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8")) == manifest
    assert [manifest["splits"][s]["components"] for s in ms.SPLITS] == [21, 3, 6]
    splits = {s: read_rows(out / s / "annotations.csv") for s in ms.SPLITS}
    for split, rows in splits.items():
        assert validate_annotations(out / split / "annotations.csv") == len(rows)
    train_real = [r for r in splits["train"] if r["image_path"].startswith("images/real_")]
    train_syn = [r for r in splits["train"] if r["image_path"].startswith("images/syn_")]
    assert len(train_real) + len(train_syn) == len(splits["train"])
    assert len(train_syn) == len(train_real) == manifest["splits"]["train"]["real"]
    assert manifest["splits"]["train"]["synthetic"] == len(train_syn)
    for split in ("val", "test"):
        assert all(r["image_path"].startswith("images/real_") for r in splits[split])
        groups = read_rows(out / split / "groups.csv")
        assert [g["image_path"] for g in groups] == [r["image_path"] for r in splits[split]]
        assert len({g["group_id"] for g in groups}) == manifest["splits"][split]["components"]
    assert len(train_real) + len(splits["val"]) + len(splits["test"]) == 32
    texts = {s: {r["plate_text"] for r in rows if r["image_path"].startswith("images/real_")}
             for s, rows in splits.items()}
    assert not texts["train"] & texts["val"] and not texts["train"] & texts["test"] and not texts["val"] & texts["test"]
    where = {r["plate_text"]: s for s, rows in splits.items() for r in rows if r["image_path"].startswith("images/real_")}
    assert where["CAR900"] == where["CAR001"]
    assert all(r["plate_text"] != "ZZZ999" for rows in splits.values() for r in rows)
    assert manifest["moto_target_met"] is True and manifest["train_moto_fraction"] >= 0.2
    assert (out.stat().st_mode & 0o777) == 0o700
    assert (out / "manifest.json").stat().st_mode & 0o777 == 0o600
    assert (out / "train" / "images" / "real_000000.png").stat().st_mode & 0o777 == 0o600
    with pytest.raises(TrainingError):
        md.build_mix(out, [real], syn, 0.1, 0.2, 1.0, 0.2, 0)
    with pytest.raises(TrainingError):
        md.build_mix(tmp_path.parent / "fuera_039", [real], syn, 0.1, 0.2, 1.0, 0.2, 0)
    with pytest.raises(TrainingError):
        md.build_mix(tmp_path / "mix2", [out], None, 0.1, 0.2, 1.0, 0.2, 0)
    assert not (tmp_path / "mix2").exists()


def test_build_mix_is_deterministic_and_split_ignores_synthetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(md, "DATASETS_DIR", tmp_path)
    real, syn = real_source(tmp_path), synthetic_source(tmp_path)
    md.build_mix(tmp_path / "a", [real], syn, 0.1, 0.2, 1.0, 0.2, 0)
    md.build_mix(tmp_path / "b", [real], syn, 0.1, 0.2, 1.0, 0.2, 0)
    md.build_mix(tmp_path / "c", [real], None, 0.1, 0.2, 1.0, 0.2, 0)
    for split in ms.SPLITS:
        first = (tmp_path / "a" / split / "annotations.csv").read_text(encoding="utf-8")
        assert first == (tmp_path / "b" / split / "annotations.csv").read_text(encoding="utf-8")
    for split in ("val", "test"):
        assert (tmp_path / "a" / split / "annotations.csv").read_text(encoding="utf-8") == \
            (tmp_path / "c" / split / "annotations.csv").read_text(encoding="utf-8")


def test_main_prints_no_plate_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(md, "DATASETS_DIR", tmp_path)
    real_source(tmp_path)
    synthetic_source(tmp_path)
    assert md.main(["--real", "real1", "--synthetic", "syn", "--output", "mix_cli"]) == 0
    printed = capsys.readouterr().out
    assert "train:" in printed and "test:" in printed
    assert "CAR" not in printed and "MOT" not in printed and "SYN" not in printed
