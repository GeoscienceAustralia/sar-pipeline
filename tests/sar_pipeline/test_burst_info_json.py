from datetime import datetime
import json
from unittest import mock

import pytest
import shapely

from sar_pipeline.pipelines.isce3_rtc import cli
from sar_pipeline.pipelines.isce3_rtc.utils.burst_utils import (
    read_burst_info_json,
    write_burst_info_json,
)

SCENE = "S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD"


@pytest.fixture
def burst_info():
    return {
        "t070_149815_iw2": {
            "azimuth_time": datetime(2022, 1, 1, 12, 47, 45, 123456),
            "start_time": datetime(2022, 1, 1, 12, 47, 44, 500000),
            "end_time": datetime(2022, 1, 1, 12, 47, 48, 250000),
            "geometry": shapely.geometry.box(150.0, -70.1, 151.0, -69.9),
            "pols": ["HH", "HV"],
        },
        "t070_149816_iw2": {
            "azimuth_time": datetime(2022, 1, 1, 12, 47, 48, 0),
            "start_time": datetime(2022, 1, 1, 12, 47, 47, 400000),
            "end_time": datetime(2022, 1, 1, 12, 47, 51, 100000),
            "geometry": shapely.geometry.MultiPolygon(
                [
                    shapely.geometry.box(179.5, -70.0, 180.0, -69.8),
                    shapely.geometry.box(-180.0, -70.0, -179.5, -69.8),
                ]
            ),
            "pols": ["HH"],
        },
    }


def test_burst_info_json_round_trip(tmp_path, burst_info):
    path = write_burst_info_json(burst_info, tmp_path / "burst_info.json")

    with path.open() as f:
        raw = json.load(f)
    assert raw["version"] == 1
    assert raw["source"] == "CDSE"

    loaded = read_burst_info_json(path)
    assert loaded.keys() == burst_info.keys()
    for burst_id, info in burst_info.items():
        for key in ("azimuth_time", "start_time", "end_time"):
            assert loaded[burst_id][key] == info[key]
        assert loaded[burst_id]["geometry"].equals(info["geometry"])
        assert loaded[burst_id]["pols"] == info["pols"]


def test_read_burst_info_json_rejects_unknown_version(tmp_path):
    path = tmp_path / "burst_info.json"
    path.write_text(json.dumps({"version": 99, "bursts": {}}))
    with pytest.raises(ValueError):
        read_burst_info_json(path)


def test_load_scene_burst_info_uses_saved_file(tmp_path, burst_info):
    write_burst_info_json(
        burst_info, tmp_path / cli.BURST_INFO_FILENAME.format(scene=SCENE)
    )
    with mock.patch.object(
        cli,
        "get_burst_info_for_scene_from_cdse",
        side_effect=AssertionError("CDSE should not be queried"),
    ):
        loaded = cli._load_scene_burst_info(SCENE, tmp_path)
    assert loaded.keys() == burst_info.keys()
    assert loaded["t070_149815_iw2"]["start_time"] == datetime(
        2022, 1, 1, 12, 47, 44, 500000
    )


def test_load_scene_burst_info_falls_back_to_cdse(tmp_path, burst_info):
    with mock.patch.object(
        cli, "get_burst_info_for_scene_from_cdse", return_value=burst_info
    ) as cdse:
        loaded = cli._load_scene_burst_info(SCENE, tmp_path)
    cdse.assert_called_once_with(SCENE)
    assert loaded is burst_info
