from sar_antarctica.nci.preparation.orbits import (
    parse_orbit_file_dates,
    find_latest_orbit_for_scene
)

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
