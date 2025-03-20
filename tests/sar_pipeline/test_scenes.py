import datetime
from sar_pipeline.nci.preparation.scenes import (
    parse_scene_file_dates,
    parse_scene_file_sensor,
)

import dataclasses
from datetime import datetime
from pathlib import Path
import pytest


@dataclasses.dataclass
class Scene:
    id: str
    file: Path
    sensor: str
    start_date: datetime
    stop_date: datetime


scene_1 = Scene(
    id="S1A_EW_GRDM_1SDH_20200330T165825_20200330T165929_031907_03AF02_8570",
    file=Path(
        "/g/data/fj7/Copernicus/Sentinel-1/C-SAR/GRD/2020/2020-03/70S050E-75S055E/S1A_EW_GRDM_1SDH_20200330T165825_20200330T165929_031907_03AF02_8570.zip"
    ),
    sensor="S1A",
    start_date=datetime(2020, 3, 30, 16, 58, 25),
    stop_date=datetime(2020, 3, 30, 16, 59, 29),
)

scene_2 = Scene(
    id="S1B_EW_GRDM_1SDH_20210914T112333_20210914T112403_028693_036C96_3EA8",
    file=Path(
        "/g/data/fj7/Copernicus/Sentinel-1/C-SAR/GRD/2021/2021-09/60S120E-65S125E/S1B_EW_GRDM_1SDH_20210914T112333_20210914T112403_028693_036C96_3EA8.zip"
    ),
    sensor="S1B",
    start_date=datetime(2021, 9, 14, 11, 23, 33),
    stop_date=datetime(2021, 9, 14, 11, 24, 3),
)

scenes = [scene_1, scene_2]


@pytest.mark.parametrize("scene", scenes)
def test_parse_scene_file_dates(scene: Scene):
    date_tuple = (scene.start_date, scene.stop_date)
    assert parse_scene_file_dates(scene.id) == date_tuple


@pytest.mark.parametrize("scene", scenes)
def test_parse_scene_file_sensor(scene: Scene):
    assert parse_scene_file_sensor(scene.id) == scene.sensor
