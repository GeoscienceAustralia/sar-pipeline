"""Offline tests for extracting downloaded scene zips"""

from pathlib import Path
import zipfile

import pytest

from sar_pipeline.preparation.downloads.scenes import _unzip_scene, _get_scene_path

SCENE = "S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD"
MEMBER = f"{SCENE}.SAFE/measurement/iw1.tiff"
CONTENT = b"measurement data " * 100


def _make_scene_zip(folder: Path) -> Path:
    zip_path = folder / f"{SCENE}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr(MEMBER, CONTENT)
    return zip_path


def _leftover_tmp_dirs(folder: Path) -> list[Path]:
    return list(folder.glob(".extracting_*"))


def test_unzip_scene_extracts_safe(tmp_path):
    zip_path = _make_scene_zip(tmp_path)
    safe_path = tmp_path / f"{SCENE}.SAFE"

    assert _unzip_scene(zip_path, safe_path, tmp_path) == safe_path
    assert (tmp_path / MEMBER).read_bytes() == CONTENT
    assert zip_path.exists()
    assert not _leftover_tmp_dirs(tmp_path)


def test_unzip_scene_removes_corrupt_extraction(tmp_path):
    zip_path = _make_scene_zip(tmp_path)
    safe_path = tmp_path / f"{SCENE}.SAFE"

    # corrupt the stored member data so extraction fails the CRC check
    data = zip_path.read_bytes()
    zip_path.write_bytes(data.replace(CONTENT[:20], b"X" * 20, 1))

    with pytest.raises(zipfile.BadZipFile):
        _unzip_scene(zip_path, safe_path, tmp_path)

    assert not safe_path.exists()
    assert not zip_path.exists()
    assert not _leftover_tmp_dirs(tmp_path)


def test_get_scene_path_skips_extraction(tmp_path):
    # the zip does not exist, so any extraction attempt would raise
    zip_path = tmp_path / f"{SCENE}.zip"
    safe_path = tmp_path / f"{SCENE}.SAFE"

    assert _get_scene_path(zip_path, safe_path, tmp_path, unzip=False) == zip_path
    assert not safe_path.exists()

    safe_path.mkdir()
    assert _get_scene_path(zip_path, safe_path, tmp_path, unzip=True) == safe_path
