import dataclasses
from datetime import datetime
from pathlib import Path
import pytest

from sar_pipeline.nci.preparation.orbits import (
    find_orbits,
    parse_orbit_file_dates,
    filter_orbits_to_cover_time_window,
    filter_orbits_to_latest,
    find_latest_orbit_covering_window,
    find_latest_orbit_for_scene,
)

test_location = Path(__file__).resolve().parent


orbit_directory = test_location / "data" / "orbits"
scene_id = "S1B_EW_GRDM_1SDH_20191130T165626_20191130T165726_019159_0242A2_2F58"


@dataclasses.dataclass
class Orbit:
    filename: str
    filepath: Path
    published_date: datetime
    start_date: datetime
    stop_date: datetime


orbit_1 = Orbit(
    filename="S1B_OPER_AUX_POEORB_OPOD_20191220T110516_V20191129T225942_20191201T005942.EOF",
    filepath=orbit_directory
    / "S1B_OPER_AUX_POEORB_OPOD_20191220T110516_V20191129T225942_20191201T005942.EOF",
    published_date=datetime(2019, 12, 20, 11, 5, 16),
    start_date=datetime(2019, 11, 29, 22, 59, 42),
    stop_date=datetime(2019, 12, 1, 0, 59, 42),
)

orbit_2 = Orbit(
    filename="S1B_OPER_AUX_RESORB_OPOD_20191130T180907_V20191130T140919_20191130T172649.EOF",
    filepath=orbit_directory
    / "S1B_OPER_AUX_RESORB_OPOD_20191130T180907_V20191130T140919_20191130T172649.EOF",
    published_date=datetime(2019, 11, 30, 18, 9, 7),
    start_date=datetime(2019, 11, 30, 14, 9, 19),
    stop_date=datetime(2019, 11, 30, 17, 26, 49),
)

orbit_3 = Orbit(
    filename="S1B_OPER_AUX_RESORB_OPOD_20191130T175634_V20191130T140919_20191130T172649.EOF",
    filepath=orbit_directory
    / "S1B_OPER_AUX_RESORB_OPOD_20191130T175634_V20191130T140919_20191130T172649.EOF",
    published_date=datetime(2019, 11, 30, 17, 56, 34),
    start_date=datetime(2019, 11, 30, 14, 9, 19),
    stop_date=datetime(2019, 11, 30, 17, 26, 49),
)

orbit_4 = Orbit(
    filename="S1B_OPER_AUX_RESORB_OPOD_20191130T210136_V20191130T154804_20191130T190534.EOF",
    filepath=orbit_directory
    / "S1B_OPER_AUX_RESORB_OPOD_20191130T210136_V20191130T154804_20191130T190534.EOF",
    published_date=datetime(2019, 11, 30, 21, 1, 36),
    start_date=datetime(2019, 11, 30, 15, 48, 4),
    stop_date=datetime(2019, 11, 30, 19, 5, 34),
)


test_orbits = [orbit_1, orbit_2, orbit_3, orbit_4]
orbit_filenames = [orbit.filename for orbit in test_orbits]
orbit_filepaths = [orbit_directory / file for file in orbit_filenames]
orbit_files_and_published_dates = [
    {"orbit": orbit.filepath, "published_date": orbit.published_date}
    for orbit in test_orbits
]


def test_find_orbits():
    orbit_files = find_orbits([orbit_directory])
    assert set(orbit_files) == set(orbit_filepaths)


@pytest.mark.parametrize("orbit", test_orbits)
def test_parse_orbit_file_dates(orbit):
    published, start, stop = parse_orbit_file_dates(orbit.filename)
    assert published == orbit.published_date
    assert start == orbit.start_date
    assert stop == orbit.stop_date


def test_filter_orbits_to_cover_time_window():

    assert filter_orbits_to_cover_time_window(
        orbit_filepaths,
        datetime(2019, 11, 30, 18, 0, 0),
        datetime(2019, 11, 30, 18, 1, 0),
    ) == [orbit_files_and_published_dates[0], orbit_files_and_published_dates[3]]

    assert (
        filter_orbits_to_cover_time_window(
            orbit_filepaths,
            datetime(2019, 11, 30, 16, 56, 26),
            datetime(2019, 11, 30, 16, 57, 26),
        )
        == orbit_files_and_published_dates
    )


def test_filter_orbits_to_latest():
    assert filter_orbits_to_latest(orbit_files_and_published_dates) == orbit_1.filepath


def test_find_latest_orbit_covering_window():
    assert (
        find_latest_orbit_covering_window(
            orbit_filepaths,
            datetime(2019, 11, 30, 18, 0, 0),
            datetime(2019, 11, 30, 18, 1, 0),
        )
        == orbit_1.filepath
    )


def test_find_latest_orbit_for_scene():
    assert find_latest_orbit_for_scene(scene_id, orbit_filepaths) == orbit_1.filepath
