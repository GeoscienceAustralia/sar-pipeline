from sar_antarctica.nci.preparation.orbits import (
    parse_orbit_file_dates,
    find_latest_orbit_for_scene
)
from pathlib import Path
import pytest
import dataclasses
from datetime import datetime

@dataclasses.dataclass
class Orbit:
    file: str
    published_date: datetime
    start_date: datetime
    stop_date: datetime

orbit_1 = Orbit(
    file="S1A_OPER_AUX_POEORB_OPOD_20141207T123431_V20141115T225944_20141117T005944.EOF",
    published_date=datetime(2014, 12, 7,12,34,31),
    start_date=datetime(2014,11,15,22,59,44),
    stop_date=datetime(2014,11,17,0,59,44)
)
orbit_2 = Orbit(
    file="S1A_OPER_AUX_POEORB_OPOD_20191220T120706_V20191129T225942_20191201T005942.EOF",
    published_date=datetime(2019,12,20,12,7,6),
    start_date=datetime(2019,11,29,22,59,42),
    stop_date=datetime(2019,12,1,0,59,42)
)

orbits = [orbit_1, orbit_2]

@pytest.mark.parametrize("orbit", orbits)
def test_parse_orbit_file_dates(orbit: Orbit):
    date_tuple = (orbit.published_date, orbit.start_date, orbit.stop_date)
    assert parse_orbit_file_dates(orbit.file) == date_tuple


@dataclasses.dataclass
class Scene:
    scene_id: str
    latest_orbit: Path
    latest_res_orbit: Path
    latest_poe_orbit: Path

scene_1 = Scene(
    scene_id="S1B_EW_GRDM_1SDH_20191130T165626_20191130T165726_019159_0242A2_2F58",
    latest_orbit=Path("/g/data/fj7/Copernicus/Sentinel-1/POEORB/S1B/S1B_OPER_AUX_POEORB_OPOD_20191220T110516_V20191129T225942_20191201T005942.EOF"),
    latest_res_orbit=Path("/g/data/fj7/Copernicus/Sentinel-1/RESORB/S1B/S1B_OPER_AUX_RESORB_OPOD_20191130T210136_V20191130T154804_20191130T190534.EOF"),
    latest_poe_orbit=Path("/g/data/fj7/Copernicus/Sentinel-1/POEORB/S1B/S1B_OPER_AUX_POEORB_OPOD_20191220T110516_V20191129T225942_20191201T005942.EOF")
)

scene_2 = Scene(
    scene_id="S1A_EW_GRDM_1SDH_20220612T120348_20220612T120452_043629_053582_0F66",
    latest_orbit=Path("/g/data/fj7/Copernicus/Sentinel-1/POEORB/S1A/S1A_OPER_AUX_POEORB_OPOD_20220702T081845_V20220611T225942_20220613T005942.EOF"),
    latest_res_orbit=Path("/g/data/fj7/Copernicus/Sentinel-1/RESORB/S1A/S1A_OPER_AUX_RESORB_OPOD_20220612T143829_V20220612T104432_20220612T140202.EOF"),
    latest_poe_orbit=Path("/g/data/fj7/Copernicus/Sentinel-1/POEORB/S1A/S1A_OPER_AUX_POEORB_OPOD_20220702T081845_V20220611T225942_20220613T005942.EOF")
)

scenes = [scene_1, scene_2]

@pytest.mark.parametrize("scene", scenes)
def test_find_latest_orbit_for_scene(scene: Scene):
    assert find_latest_orbit_for_scene(scene.scene_id) == scene.latest_orbit
    assert find_latest_orbit_for_scene(scene.scene_id, orbit_type="RES") == scene.latest_res_orbit
    assert find_latest_orbit_for_scene(scene.scene_id, orbit_type="POE") == scene.latest_poe_orbit
