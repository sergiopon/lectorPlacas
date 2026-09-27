from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from lector_placas.domain.errors import ConfigurationError, DatasetError, UnsafePathError
from lector_placas.infrastructure.dataset_fetcher import (
    api_key_from_env,
    download_dataset,
    export_link,
    extract_zip,
    latest_version,
)

KEY = "clave-sintetica-123"


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class FakeHttp:
    def __init__(self, responses: dict[str, list[tuple[int, bytes]]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float) -> tuple[int, bytes]:
        self.calls.append(url)
        for prefix, queue in self.responses.items():
            if url.startswith(prefix):
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"URL inesperada: {url}")


PROJECT = "https://api.roboflow.com/ws/proj?"
EXPORT = "https://api.roboflow.com/ws/proj/7/yolov8?"
LINK = "https://storage.example.org/export.zip"


def test_api_key_from_env() -> None:
    assert api_key_from_env({"ROBOFLOW_API_KEY": KEY}) == KEY
    with pytest.raises(ConfigurationError):
        api_key_from_env({})


def test_latest_version_picks_max_and_hides_key() -> None:
    body = json.dumps({"versions": [{"id": "ws/proj/3"}, {"id": "ws/proj/7"}]}).encode()
    assert latest_version(FakeHttp({PROJECT: [(200, body)]}), KEY, "ws", "proj") == 7
    with pytest.raises(DatasetError) as error:
        latest_version(FakeHttp({PROJECT: [(401, b"{}")]}), KEY, "ws", "proj")
    assert KEY not in str(error.value)
    with pytest.raises(DatasetError):
        latest_version(
            FakeHttp({PROJECT: [(200, b'{"versions": [{"id": "x/y/z"}]}')]}), KEY, "ws", "proj"
        )


def test_export_link_polls_until_ready() -> None:
    ready = json.dumps({"export": {"link": LINK}}).encode()
    http = FakeHttp(
        {EXPORT: [(202, b'{"progress": 0.5}'), (202, b'{"progress": 0.9}'), (200, ready)]}
    )
    sleeps: list[float] = []
    assert export_link(http, KEY, "ws", "proj", 7, "yolov8", sleeps.append) == LINK
    assert sleeps == [2.0, 2.0]
    assert all("nocache=true" in url for url in http.calls)


def test_export_link_rejects_non_https() -> None:
    bad = json.dumps({"export": {"link": "http://inseguro/x.zip"}}).encode()
    with pytest.raises(DatasetError):
        export_link(
            FakeHttp({EXPORT: [(200, bad)]}), KEY, "ws", "proj", 7, "yolov8", lambda s: None
        )


def test_extract_zip_blocks_zip_slip(tmp_path: Path) -> None:
    extract_zip(
        zip_bytes({"data.yaml": b"names: [placa]\n", "train/images/a.jpg": b"x"}), tmp_path / "ok"
    )
    assert (tmp_path / "ok" / "data.yaml").exists()
    with pytest.raises(UnsafePathError):
        extract_zip(zip_bytes({"../fuera.txt": b"x"}), tmp_path / "malo")
    assert not (tmp_path / "fuera.txt").exists()
    with pytest.raises(DatasetError):
        extract_zip(b"no es zip", tmp_path / "roto")


def test_download_dataset_end_to_end(tmp_path: Path) -> None:
    project = json.dumps({"versions": [{"id": "ws/proj/7"}]}).encode()
    ready = json.dumps({"export": {"link": LINK}}).encode()
    http = FakeHttp(
        {
            PROJECT: [(200, project)],
            EXPORT: [(200, ready)],
            LINK: [(200, zip_bytes({"data.yaml": b"names: [placa]\n"}))],
        }
    )
    assert download_dataset(http, KEY, "ws", "proj", "yolov8", tmp_path / "d", lambda s: None) == 7
    assert (tmp_path / "d" / "data.yaml").read_text() == "names: [placa]\n"
