from sar_antarctica.nci.preparation.orbits import find_latest_orbit_for_scene
from sar_antarctica.nci.preparation.scenes import find_scene_file_from_id

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
    latest_orbit: Path
    latest_poe_orbit: Path
    latest_res_orbit: Path


scene_1 = Scene(
    id="S1A_EW_GRDM_1SDH_20220612T120348_20220612T120452_043629_053582_0F66",
    file=Path(
        "/g/data/fj7/Copernicus/Sentinel-1/C-SAR/GRD/2022/2022-06/65S115E-70S120E/S1A_EW_GRDM_1SDH_20220612T120348_20220612T120452_043629_053582_0F66.zip"
    ),
    sensor="S1A",
    start_date=datetime(2022, 6, 12, 12, 3, 48),
    stop_date=datetime(2022, 6, 12, 12, 4, 52),
    latest_orbit=Path(
        "/g/data/fj7/Copernicus/Sentinel-1/POEORB/S1A/S1A_OPER_AUX_POEORB_OPOD_20220702T081845_V20220611T225942_20220613T005942.EOF"
    ),
    latest_poe_orbit=Path(
        "/g/data/fj7/Copernicus/Sentinel-1/POEORB/S1A/S1A_OPER_AUX_POEORB_OPOD_20220702T081845_V20220611T225942_20220613T005942.EOF"
    ),
    latest_res_orbit=Path(
        "/g/data/fj7/Copernicus/Sentinel-1/RESORB/S1A/S1A_OPER_AUX_RESORB_OPOD_20220612T143829_V20220612T104432_20220612T140202.EOF"
    ),
)

scene_2 = Scene(
    id="S1B_EW_GRDM_1SDH_20191130T165626_20191130T165726_019159_0242A2_2F58",
    file=Path(
        "/g/data/fj7/Copernicus/Sentinel-1/C-SAR/GRD/2019/2019-11/65S160E-70S165E/S1B_EW_GRDM_1SDH_20191130T165626_20191130T165726_019159_0242A2_2F58.zip"
    ),
    sensor="S1B",
    start_date=datetime(2019, 11, 30, 16, 56, 26),
    stop_date=datetime(2019, 11, 30, 16, 57, 26),
    latest_orbit=Path(
        "/g/data/fj7/Copernicus/Sentinel-1/POEORB/S1B/S1B_OPER_AUX_POEORB_OPOD_20191220T110516_V20191129T225942_20191201T005942.EOF"
    ),
    latest_poe_orbit=Path(
        "/g/data/fj7/Copernicus/Sentinel-1/POEORB/S1B/S1B_OPER_AUX_POEORB_OPOD_20191220T110516_V20191129T225942_20191201T005942.EOF"
    ),
    latest_res_orbit=Path(
        "/g/data/fj7/Copernicus/Sentinel-1/RESORB/S1B/S1B_OPER_AUX_RESORB_OPOD_20191130T210136_V20191130T154804_20191130T190534.EOF"
    ),
)

scenes = [scene_1, scene_2]


@pytest.mark.parametrize("scene", scenes)
def test_find_latest_orbit_for_scene(scene: Scene):
    scene_list = [scene.latest_poe_orbit, scene.latest_res_orbit]
    assert find_latest_orbit_for_scene(scene.id, scene_list) == scene.latest_orbit


@pytest.mark.parametrize("scene", scenes)
def test_find_scene_file_from_id(scene: Scene):
    assert find_scene_file_from_id(scene.id) == scene.file
