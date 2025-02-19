from sar_pipeline.nci.preparation.dem import (
    get_cop30_dem_for_bounds,
    check_s1_bounds_cross_antimeridian,
    get_target_antimeridian_projection,
    split_s1_bounds_at_am_crossing,
    adjust_bounds_at_high_lat,
    find_required_dem_paths_from_index,
)
from sar_pipeline.nci.preparation.create_dem_vrt import find_tiles, build_tileindex
from sar_pipeline.utils.spatial import BoundingBox
from dataclasses import dataclass
import rasterio
from pathlib import Path
from numpy.testing import assert_allclose
import pytest
import shutil


CURRENT_DIR = Path(__file__).parent.resolve()
FOLDER_PATH = CURRENT_DIR / "data/copernicus_30m_world"
GEOID_PATH = (
    CURRENT_DIR
    / "data/geoid/tests/sar_pipeline/data/geoid/us_nga_egm2008_1_4326__agisoft_clipped.tif"
)
TMP_PATH = CURRENT_DIR / "TMP"


@dataclass
class TestDem:
    requested_bounds: tuple[float, float, float, float]
    bounds_array_file: str


@dataclass
class TestAntimeridianDem(TestDem):
    crosses_antimeridian: bool
    western_hemisphere_bounds_4326: tuple[float, float, float, float]
    eastern_hemisphere_bounds_4326: tuple[float, float, float, float]
    target_projection: int


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

test_dem_antimeridian_western = TestDem(
    (-180, -79.59302, -179.99817, -79.59171),
    TEST_DATA_PATH / "antimeridian_S80_WEST_4326_0_2130_3_6.tif",
)

test_dem_antimeridian_eastern = TestDem(
    (179.99705, -79.59302, 179.99958333333333, -79.59171),
    TEST_DATA_PATH / "antimeridian_S80_EAST_4326_2396_2130_4_6.tif",
)

test_dem_antimeridian_crossing = TestAntimeridianDem(
    (-179.99817, -79.59302, 179.99705, -79.59171),
    "",
    True,
    test_dem_antimeridian_western.requested_bounds,
    test_dem_antimeridian_eastern.requested_bounds,
    3031,
)


test_dems = [
    test_single_tile_ocean_in_tile,
    test_single_tile_land_in_tile,
    test_dem_three_tiles_and_ocean,
    test_dem_two_tiles_same_latitude,
    test_dem_antimeridian_western,
    test_dem_antimeridian_eastern,
]

test_antimeridian_dems = [test_dem_antimeridian_crossing]


@pytest.mark.parametrize("test_input", test_dems)
def test_get_cop30_dem_for_bounds_ocean_and_land(test_input: TestDem):

    bounds = test_input.requested_bounds
    bounds_array_file = test_input.bounds_array_file

    # Create the temporary directory to store intermediate outputs
    if not TMP_PATH.exists():
        TMP_PATH.mkdir(parents=True, exist_ok=True)

    SAVE_PATH = TMP_PATH / Path("TMP.tif")
    INDEX_PATH = TMP_PATH / Path("TMP.gpkg")

    # Find relevant test tiles and build tile index
    TEST_TILES = find_tiles(FOLDER_PATH, "Copernicus_DSM_COG_10_???_00_????_00_DEM")
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

    # Once complete, remove the TMP files and directory
    shutil.rmtree(TMP_PATH)


@pytest.mark.parametrize("test_input", test_antimeridian_dems)
def test_check_s1_bounds_cross_antimeridian(test_input):
    assert (
        check_s1_bounds_cross_antimeridian(test_input.requested_bounds)
        == test_input.crosses_antimeridian
    )


@pytest.mark.parametrize("test_input", test_antimeridian_dems)
def test_get_target_antimeridian_projection(test_input):
    assert (
        get_target_antimeridian_projection(test_input.requested_bounds)
        == test_input.target_projection
    )


@pytest.mark.parametrize("test_input", test_antimeridian_dems)
def test_split_s1_bounds_at_am_crossing(test_input):

    eastern_bounds, western_bounds = split_s1_bounds_at_am_crossing(
        test_input.requested_bounds
    )

    assert eastern_bounds == BoundingBox(*test_input.eastern_hemisphere_bounds_4326)
    assert western_bounds == BoundingBox(*test_input.western_hemisphere_bounds_4326)
