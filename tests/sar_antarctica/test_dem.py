from sar_antarctica.nci.preparation.dem import (
    get_cop30_dem_for_bounds,
    check_s1_bounds_cross_antimeridian,
    get_target_antimeridian_projection,
    split_s1_bounds_at_am_crossing,
    adjust_bounds_at_high_lat,
    find_required_dem_paths_from_index,
)
from sar_antarctica.nci.preparation.create_dem_vrt import find_tiles, build_tileindex
from dataclasses import dataclass
import rasterio
from pathlib import Path
from numpy.testing import assert_allclose
import pytest


CURRENT_DIR = Path(__file__).parent.resolve()


@dataclass
class TestDem:
    requested_bounds: tuple[float, float, float, float]
    bounds_array_file: str


TEST_DATA_PATH = CURRENT_DIR / "data/copernicus_30m_world/"
test_single_tile_ocean_in_tile = TestDem(
    (161.00062, -69.00084, 161.002205, -69.00027),
    str(TEST_DATA_PATH / "cop_dem_ocean_and_land_1_1_4_3.tif"),
)

test_single_tile_land_in_tile = TestDem(
    (162.67257663025052, -70.73588517869858, 162.67516972746182, -70.73474602514219),
    str(TEST_DATA_PATH / "cop_dem_S71_2007_2645_4_5.tif"),
)

test_dem_three_tiles_and_ocean = TestDem(
    (161.9981536608549, -70.00076846229373, 162.00141174891965, -69.99912324943375),
    TEST_DATA_PATH / "cop_dem_ocean_and_land_1797_3597_7_7.tif",
)
test_dem_two_tiles_same_latitude = TestDem(
    (161.96252, -70.75924, 162.10388, -70.72293),
    TEST_DATA_PATH / "cop_dem_S71_1155_2603_171_131.tif",
)


test_dems = [
    test_single_tile_ocean_in_tile,
    test_single_tile_land_in_tile,
    test_dem_three_tiles_and_ocean,
    test_dem_two_tiles_same_latitude,
]


FOLDER_PATH = CURRENT_DIR / "data/copernicus_30m_world"
GEOID_PATH = (
    CURRENT_DIR
    / "data/geoid/tests/sar_antarctica/data/geoid/us_nga_egm2008_1_4326__agisoft_clipped.tif"
)


@pytest.mark.parametrize("test_input", test_dems)
def test_get_cop30_dem_for_bounds_ocean_and_land(test_input: TestDem):

    bounds = test_input.requested_bounds
    bounds_array_file = test_input.bounds_array_file

    SAVE_PATH = CURRENT_DIR / Path("TMP") / Path("TMP.tif")
    INDEX_PATH = CURRENT_DIR / Path("TMP") / Path("TMP.gpkg")

    # Find relevant test tiles and build tile index
    TEST_TILES = find_tiles(FOLDER_PATH, "Copernicus_DSM_COG_10_S??_00_E16?_00_DEM")
    build_tileindex(
        TEST_TILES,
        INDEX_PATH,
    )

    array, profile = get_cop30_dem_for_bounds(
        bounds,
        save_path=SAVE_PATH,
        ellipsoid_heights=False,
        adjust_at_high_lat=False,
        buffer_pixels=None,
        buffer_world=None,
        cop30_index_path=INDEX_PATH,
        cop30_folder_path=None,
        geoid_tif_path=GEOID_PATH,
    )

    with rasterio.open(bounds_array_file, "r") as src:
        expected_array = src.read(1)

    assert_allclose(array, expected_array)
