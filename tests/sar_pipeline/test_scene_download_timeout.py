"""Offline tests for the per-source scene download timeout.

The download for each source runs in a forked child process, so patches of
`download_scene_from_preference_list` apply in the child. The child cannot
update objects in the test process, so the fake download records each
attempt by appending to a file in tmp_path.
"""

import os
import subprocess
import time
from pathlib import Path
from unittest import mock

import pytest
import shapely

from sar_pipeline.preparation.downloads import scenes
from sar_pipeline.preparation.downloads.scenes import (
    SceneDownloadError,
    SceneDownloadTimeoutError,
    download_scene_from_preference_list_with_timeout,
)

SCENE = "S1A_IW_SLC__1SDV_20220101T000000_20220101T000030_041234_04E7A2_ABCD"
# 1.5 seconds per source
TIMEOUT_MINS = 1.5 / 60


def _make_fake_download(tmp_path: Path, behaviours: dict):
    """Fake `download_scene_from_preference_list` for a single source.
    behaviours maps a source to "ok", "raise", "sleep", "orphan" or "partial".
    """
    attempts_file = tmp_path / "attempts.txt"

    def fake_download(scene_data_source_preferences, scene, download_folder, unzip):
        (source,) = scene_data_source_preferences
        download_folder = Path(download_folder)
        with open(attempts_file, "a") as f:
            zip_exists = (download_folder / f"{scene}.zip").exists()
            f.write(f"{source},{zip_exists}\n")
        behaviour = behaviours[source]
        if behaviour == "ok":
            return (
                download_folder / f"{scene}.SAFE",
                shapely.geometry.Point(1, 2),
                f"https://{source}/{scene}",
            )
        if behaviour == "raise":
            raise SceneDownloadError(f"{source} failed")
        if behaviour == "orphan":
            # a subprocess in the same process group, like the pygssearch download
            proc = subprocess.Popen("sleep 60", shell=True)
            (tmp_path / "grandchild.pid").write_text(str(proc.pid))
        if behaviour == "partial":
            (download_folder / f"{scene}.zip").write_bytes(b"partial zip")
            (download_folder / ".extracting_abc").mkdir()
        time.sleep(60)

    return fake_download, attempts_file


def _attempts(attempts_file: Path) -> list[tuple[str, bool]]:
    lines = attempts_file.read_text().splitlines()
    return [(s, z == "True") for s, z in (line.split(",") for line in lines)]


def _run(tmp_path, sources, behaviours, **kwargs):
    fake, attempts_file = _make_fake_download(tmp_path, behaviours)
    with mock.patch.object(scenes, "download_scene_from_preference_list", fake):
        result = download_scene_from_preference_list_with_timeout(
            scene_data_source_preferences=sources,
            scene=SCENE,
            download_folder=tmp_path,
            unzip=True,
            **dict(dict(timeout_mins=TIMEOUT_MINS), **kwargs),
        )
    return result, attempts_file


def test_timed_out_source_moves_to_next(tmp_path):
    result, attempts_file = _run(
        tmp_path, ["AUS_COP_HUB", "ASF"], {"AUS_COP_HUB": "sleep", "ASF": "ok"}
    )
    path, geometry, url = result
    assert path == tmp_path / f"{SCENE}.SAFE"
    assert geometry.equals(shapely.geometry.Point(1, 2))
    assert url == f"https://ASF/{SCENE}"
    assert [s for s, _ in _attempts(attempts_file)] == ["AUS_COP_HUB", "ASF"]


def test_stalled_source_is_not_retried(tmp_path):
    # the previous implementation dropped the first source on timeout and
    # retried the list, so a stalled second source was attempted twice
    start = time.monotonic()
    result, attempts_file = _run(
        tmp_path,
        ["AUS_COP_HUB", "ASF", "CDSE"],
        {"AUS_COP_HUB": "raise", "ASF": "sleep", "CDSE": "ok"},
    )
    assert result[2] == f"https://CDSE/{SCENE}"
    assert [s for s, _ in _attempts(attempts_file)] == ["AUS_COP_HUB", "ASF", "CDSE"]
    # one timeout only
    assert time.monotonic() - start < 2 * TIMEOUT_MINS * 60


def test_all_sources_time_out_exits_with_code(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        _run(tmp_path, ["ASF", "CDSE"], {"ASF": "sleep", "CDSE": "sleep"})
    assert exc_info.value.code == 102


def test_all_sources_time_out_raises_without_exit_code(tmp_path):
    with pytest.raises(SceneDownloadTimeoutError):
        _run(
            tmp_path,
            ["ASF", "CDSE"],
            {"ASF": "raise", "CDSE": "sleep"},
            early_exit_code=None,
        )


def test_all_sources_fail_without_timeout(tmp_path):
    with pytest.raises(SceneDownloadError) as exc_info:
        _run(tmp_path, ["ASF", "CDSE"], {"ASF": "raise", "CDSE": "raise"})
    assert not isinstance(exc_info.value, SceneDownloadTimeoutError)
    assert "CDSE failed" in str(exc_info.value.__cause__)


def _process_gone_or_zombie(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return True
    # state is the field after the parenthesised command name
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


def test_timeout_kills_subprocesses_of_source(tmp_path):
    result, _ = _run(tmp_path, ["AUS_COP_HUB", "ASF"], {"AUS_COP_HUB": "orphan", "ASF": "ok"})
    assert result[2] == f"https://ASF/{SCENE}"
    pid = int((tmp_path / "grandchild.pid").read_text())
    deadline = time.monotonic() + 5
    while not _process_gone_or_zombie(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    if not _process_gone_or_zombie(pid):
        os.kill(pid, 9)  # don't leave it running
        pytest.fail(f"subprocess {pid} of the timed out source is still running")


def test_timeout_removes_partial_files_but_keeps_existing(tmp_path):
    pre_staged_safe = tmp_path / f"{SCENE}.SAFE"
    pre_staged_safe.mkdir()
    (pre_staged_safe / "manifest.safe").write_text("pre-staged")

    result, attempts_file = _run(
        tmp_path, ["AUS_COP_HUB", "ASF"], {"AUS_COP_HUB": "partial", "ASF": "ok"}
    )
    assert result[2] == f"https://ASF/{SCENE}"
    # the next source did not see the partial zip from the timed out source
    assert _attempts(attempts_file) == [("AUS_COP_HUB", False), ("ASF", False)]
    assert not (tmp_path / f"{SCENE}.zip").exists()
    assert not (tmp_path / ".extracting_abc").exists()
    assert (pre_staged_safe / "manifest.safe").read_text() == "pre-staged"
