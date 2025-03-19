from sar_pipeline.dem.dem import (
    get_cop30_dem_for_bounds,
    get_target_antimeridian_projection,
    split_s1_bounds_at_am_crossing,
    check_s1_bounds_cross_antimeridian,
    adjust_bounds_at_high_lat,
    find_required_dem_paths_from_index,
)
from sar_pipeline.dem.create_dem_vrt import find_tiles, build_tileindex
from sar_pipeline.dem.utils.spatial import BoundingBox
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
    high_lat_bounds: tuple[float, float, float, float]
    bounds_array_file: str
    expected_tiles: list[Path]

    @property
    def expected_tile_paths(self):
        cop_prefix = "Copernicus_DSM_COG_10_"
        cop_suffix = "_DEM"
        return [
            Path(
                FOLDER_PATH.joinpath(cop_prefix + tile_id + cop_suffix).joinpath(
                    cop_prefix + tile_id + cop_suffix + ".tif"
                )
            )
            for tile_id in self.expected_tiles
        ]


@dataclass
class TestAntimeridianDem(TestDem):
    crosses_antimeridian: bool
    western_hemisphere_bounds_4326: tuple[float, float, float, float]
    eastern_hemisphere_bounds_4326: tuple[float, float, float, float]
    target_projection: int


TEST_DATA_PATH = CURRENT_DIR / "data/copernicus_30m_world/"
test_single_tile_ocean_in_tile = TestDem(
    (161.00062, -69.00084, 161.002205, -69.00027),
    (161.00013080091566, -69.00101498631649, 161.0026941537473, -69.00009501072573),
    str(TEST_DATA_PATH / "cop_dem_ocean_and_land_1_1_4_3.tif"),
    ["S70_00_E161_00"],
)

test_single_tile_land_in_tile = TestDem(
    (162.67257663025052, -70.73588517869858, 162.67516972746182, -70.73474602514219),
    (162.67159567278293, -70.73612858147426, 162.67615050789217, -70.73450261180024),
    str(TEST_DATA_PATH / "cop_dem_S71_2007_2645_4_5.tif"),
    ["S71_00_E162_00"],
)

test_dem_three_tiles_and_ocean = TestDem(
    (161.9981536608549, -70.00076846229373, 162.00141174891965, -69.99912324943375),
    (161.9967408989365, -70.00109620858649, 162.0028241938515, -69.99879548303853),
    TEST_DATA_PATH / "cop_dem_ocean_and_land_1797_3597_7_7.tif",
    ["S70_00_E161_00", "S71_00_E161_00", "S71_00_E162_00"],
)
test_dem_two_tiles_same_latitude = TestDem(
    (161.96252, -70.75924, 162.10388, -70.72293),
    (161.93010734875725, -70.77292392528076, 162.13602272149964, -70.70923165070221),
    TEST_DATA_PATH / "cop_dem_S71_1155_2603_171_131.tif",
    ["S71_00_E161_00", "S71_00_E162_00"],
)

test_dem_antimeridian_western = TestDem(
    (-180, -79.59302, -179.99817, -79.59171),
    (-180.0, -79.59302000527954, -179.99816976842416, -79.59170999471834),
    TEST_DATA_PATH / "antimeridian_S80_WEST_4326_0_2130_3_6.tif",
    ["S80_00_W180_00"],
)

test_dem_antimeridian_eastern = TestDem(
    (179.99705, -79.59302, 179.99958333333333, -79.59171),
    (179.9970496266947, -79.59302001344692, 179.9995833860534, -79.59170998654993),
    TEST_DATA_PATH / "antimeridian_S80_EAST_4326_2396_2130_4_6.tif",
    ["S80_00_E179_00"],
)

test_dem_antimeridian_crossing = TestAntimeridianDem(
    (-179.99817, -79.59302, 179.99705, -79.59171),
    (179.9970496266947, -79.59302001344692, 179.9995833860534, -79.59170998654993),
    "",
    ["S80_00_W180_00", "S80_00_E179_00"],
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
        buffer_degrees=None,
        cop30_index_path=INDEX_PATH,
        cop30_folder_path=FOLDER_PATH,
        geoid_tif_path=GEOID_PATH,
    )

    with rasterio.open(bounds_array_file, "r") as src:
        expected_array = src.read(1)

    assert_allclose(array, expected_array)

    # Once complete, remove the TMP files and directory
    shutil.rmtree(TMP_PATH)


@pytest.mark.parametrize("test_input", test_dems)
def test_find_required_dem_paths_from_index(test_input):
    # Create the temporary directory to store intermediate outputs
    if not TMP_PATH.exists():
        TMP_PATH.mkdir(parents=True, exist_ok=True)

    INDEX_PATH = TMP_PATH / Path("TMP.gpkg")

    # Find relevant test tiles and build tile index
    TEST_TILES = find_tiles(FOLDER_PATH, "Copernicus_DSM_COG_10_???_00_????_00_DEM")
    build_tileindex(
        TEST_TILES,
        INDEX_PATH,
    )

    required_dem_tiles = find_required_dem_paths_from_index(
        test_input.requested_bounds, FOLDER_PATH, search_buffer=0.0
    )

    assert set(required_dem_tiles) == set(test_input.expected_tile_paths)

    # Once complete, remove the TMP files and directory
    shutil.rmtree(TMP_PATH)


@pytest.mark.parametrize("test_input", test_dems)
def test_adjust_bounds_at_high_lat(test_input):
    assert adjust_bounds_at_high_lat(
        test_input.requested_bounds
    ).bounds == pytest.approx(test_input.high_lat_bounds)


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
