import os
import math
import pytest
import shutil
from shapely.geometry import box
import numpy as np
from pathlib import Path

from sar_antarctica.nci.preparation.dem import (
    check_s1_bounds_cross_antimeridian,
    split_s1_bounds_at_am_crossing,
    get_target_antimeridian_projection,
    make_empty_cop30m_profile,
    expand_bounds,
    get_cop30_dem_for_bounds,
    find_required_dem_paths_from_index,
    find_required_dem_tile_paths_by_filename,
)
from sar_antarctica.nci.preparation.create_dem_vrt import find_tiles, build_tileindex
from sar_antarctica.nci.preparation.geoid import remove_geoid
from sar_antarctica.utils.raster import (
    merge_raster_files,
    bounds_from_profile,
    expand_raster_to_bounds,
)
from data.cop30m_profile import TEST_COP30_PROFILE_1, TEST_COP30_PROFILE_2

CURRENT_DIR = Path(os.path.abspath(__file__)).parent.resolve()

TEST_COP30_FOLDER_PATH = CURRENT_DIR / Path("data/copernicus_30m_world")
TEST_COP30_INDEX_PATH = CURRENT_DIR / Path(
    "data/copernicus_30m_world/copdem_tindex_test.gpkg"
)
TEST_GEOID_TIF_PATH = CURRENT_DIR / Path(
    "data/geoid/us_nga_egm2008_1_4326__agisoft_clipped.tif"
)

# TEST_COP30_FOLDER_PATH = Path('/g/data/v10/eoancillarydata-2/elevation/copernicus_30m_world/')
# TEST_COP30_INDEX_PATH = Path('/g/data/yp75/projects/ancillary/dem/copdem_tindex.gpkg') # disable test_make_test_gpkg
# TEST_GEOID_TIF_PATH = Path('/g/data/yp75/projects/ancillary/geoid/us_nga_egm2008_1_4326__agisoft.tif')


def test_pytest():
    assert True


def test_make_test_gpkg():
    """required to pass for other tests utilising index file"""
    tiles = find_tiles(TEST_COP30_FOLDER_PATH, pattern="*.tif")
    build_tileindex(tiles, TEST_COP30_INDEX_PATH)
    assert os.path.exists(TEST_COP30_INDEX_PATH)


@pytest.mark.parametrize(
    "bounds, expected",
    [
        (
            (163.121597, -78.632782, 172.382263, -76.383263),
            False,
        ),  # Bounds that do not cross the antimeridian
        ((170, -70, 180, -76), False),  # Bounds that do not cross the antimeridian
        ((-180, 10, -175, 20), False),  # Bounds that do not cross the antimeridian
        (
            (-177.884048, -78.176201, 178.838364, -75.697151),
            True,
        ),  # Bounds that cross the antimeridian
    ],
)
def test_check_s1_bounds_cross_antimeridian(bounds, expected):
    assert check_s1_bounds_cross_antimeridian(bounds) == expected


@pytest.mark.parametrize(
    "bounds, lat_buff, expected_left, expected_right",
    [
        (
            (-177.884048, -78.176201, 178.838364, -75.697151),
            0,
            (-180, -78.176201, -177.884048, -75.697151),
            (178.838364, -78.176201, 180, -75.697151),
        ),
        (
            (-177.884048, -78.176201, 178.838364, -75.697151),
            0.1,
            (-180, -78.276201, -177.884048, -75.597151),
            (178.838364, -78.276201, 180, -75.597151),
        ),
    ],
)
def test_split_bounds_at_am_crossing(bounds, lat_buff, expected_left, expected_right):
    left, right = split_s1_bounds_at_am_crossing(bounds, lat_buff)
    # use pytest.approx to get around small rounding errors with floats
    assert all(a == pytest.approx(b, rel=1e-9) for a, b in zip(left, expected_left))
    assert all(a == pytest.approx(b, rel=1e-9) for a, b in zip(right, expected_right))


@pytest.mark.parametrize(
    "bounds, target_crs",
    [
        ((-177.884048, -78.176201, 178.838364, -75.697151), 3031),  # antarctic
        ((-177.884048, 78.176201, 178.838364, 75.697151), 3995),  # arctic
        ((-177.884048, -1, 178.838364, 1), 32601),  # centre slight left of equator
        ((-178.884048, -1, 177.838364, 1), 32660),  # centre slight right of equator
    ],
)
def test_get_target_antimeridian_projection(bounds, target_crs):
    assert get_target_antimeridian_projection(bounds) == target_crs


@pytest.mark.parametrize(
    "bounds_to_profile", [TEST_COP30_PROFILE_1, TEST_COP30_PROFILE_2]
)
def test_make_empty_cop30m_profile(bounds_to_profile):
    bounds, target_profile = bounds_to_profile
    profile = make_empty_cop30m_profile(bounds)
    for key in profile.keys():
        if (
            isinstance(profile[key], float)
            and math.isnan(profile[key])
            and isinstance(target_profile[key], float)
            and math.isnan(target_profile[key])
        ):
            # Handle NaN comparison
            continue
        assert profile[key] == target_profile[key]


@pytest.mark.parametrize(
    "bounds, trg_shape", [((-179.9, -79.2, -179.1, -79.1), (1, 362, 962))]
)
def test_make_empty_cop30_dem(bounds, trg_shape):
    fill_value = 0
    empty_dem_profile = make_empty_cop30m_profile(bounds)
    dem_arr, dem_profile = expand_raster_to_bounds(
        bounds,
        src_profile=empty_dem_profile,
        fill_value=fill_value,
        buffer_pixels=1,
        save_path="empty.tif",
    )
    dem_bounds = bounds_from_profile(dem_profile)
    assert box(*bounds).within(box(*dem_bounds))
    assert dem_arr.shape == trg_shape


@pytest.mark.parametrize(
    "bounds, buffer, expanded_bounds",
    [
        (
            (179.1, -79.2, 179.9, -79.1),
            0,
            (179.09161, -79.201308, 179.900922, -79.09867),
        ),
        (
            (179.1, -79.2, 179.9, -79.1),
            0.01,
            (179.08161, -79.21130, 179.91092, -79.08867),
        ),
        ((10, -65.2, 20, -60), 0, (8.23494, -66.27035, 23.91474, -58.78356)),
        ((10, -65.2, 20, -60), 0, (8.23494, -66.27035, 23.91474, -58.78356)),
        ((-90, -85, -80, -80), 0, (-90, -85.07587, -70.54166, -79.85109)),
    ],
)
def test_expand_bounds(bounds, buffer, expanded_bounds):
    new_bounds = expand_bounds(bounds, buffer=buffer)
    assert pytest.approx(new_bounds[0], rel=1e-5) == pytest.approx(
        expanded_bounds[0], rel=1e-5
    )
    assert pytest.approx(new_bounds[1], rel=1e-5) == pytest.approx(
        expanded_bounds[1], rel=1e-5
    )
    assert pytest.approx(new_bounds[2], rel=1e-5) == pytest.approx(
        expanded_bounds[2], rel=1e-5
    )
    assert pytest.approx(new_bounds[3], rel=1e-5) == pytest.approx(
        expanded_bounds[3], rel=1e-5
    )


@pytest.mark.parametrize(
    "bounds, search_buffer, expected_tiles",
    [
        ((176.1, -79.2, 176.9, -79.1), 0, []),
        (
            (179.1, -79.2, 179.9, -79.1),
            0,
            [
                str(
                    TEST_COP30_FOLDER_PATH
                    / "Copernicus_DSM_COG_10_S80_00_E179_00_DEM.tif"
                )
            ],
        ),
        (
            (179.1, -79.2, 179.9, -79.1),
            0.3,
            [
                str(
                    TEST_COP30_FOLDER_PATH
                    / "Copernicus_DSM_COG_10_S80_00_E178_00_DEM.tif"
                ),
                str(
                    TEST_COP30_FOLDER_PATH
                    / "Copernicus_DSM_COG_10_S80_00_E179_00_DEM.tif"
                ),
            ],
        ),
        (
            (178.1, -79.2, 179.9, -79.1),
            0,
            [
                str(
                    TEST_COP30_FOLDER_PATH
                    / "Copernicus_DSM_COG_10_S80_00_E178_00_DEM.tif"
                ),
                str(
                    TEST_COP30_FOLDER_PATH
                    / "Copernicus_DSM_COG_10_S80_00_E179_00_DEM.tif"
                ),
            ],
        ),
    ],
)
def test_find_required_dem_paths(bounds, search_buffer, expected_tiles):
    # limited to files in TEST_COP30_FOLDER_PATH
    tiles_from_folder = find_required_dem_tile_paths_by_filename(
        bounds,
        cop30_folder_path=TEST_COP30_FOLDER_PATH,
        search_buffer=search_buffer,
        tifs_in_subfolder=False,
    )
    tiles_from_index = find_required_dem_paths_from_index(
        bounds, cop30_index_path=TEST_COP30_INDEX_PATH, search_buffer=search_buffer
    )
    assert tiles_from_folder == expected_tiles
    assert tiles_from_index == expected_tiles
    assert tiles_from_folder == tiles_from_index


@pytest.mark.parametrize(
    "bounds, trg_shape, buffer_pixels",
    [
        ((-179.9, -79.2, -179.1, -79.1), (1, 362, 962), 0),
        ((-179.9, -79.2, -179.1, -79.1), (1, 370, 970), 4),
        ((-179.6, -79.9, -179.4, -79.5), (1, 1442, 242), 0),
        ((179.1, -79.2, 179.9, -79.1), (1, 362, 962), 0),
        ((179.5, -79.2, 179.6, -79.01), (1, 690, 126), 2),
        ((179.5, -79.2, 179.6, -79.01), (1, 688, 124), 1),
        ((178.1, -79.2, 179.95, -79.1), (1, 362, 2222), 0),
        ((178.1, -79.2, 179.95, -79.1), (1, 366, 2226), 2),
    ],
)
def test_dem_read_for_bounds(bounds, trg_shape, buffer_pixels):
    os.makedirs(CURRENT_DIR / Path("TMP"), exist_ok=True)
    dem_tiles = find_required_dem_paths_from_index(
        bounds, cop30_index_path=TEST_COP30_INDEX_PATH
    )
    dem_arr, dem_profile = merge_raster_files(
        dem_tiles,
        output_path=CURRENT_DIR / Path("TMP") / Path("TMP.tif"),
        bounds=bounds,
        buffer_pixels=buffer_pixels,
    )
    shutil.rmtree(CURRENT_DIR / Path("TMP"))
    dem_bounds = bounds_from_profile(dem_profile)
    assert box(*bounds).within(box(*dem_bounds))
    assert dem_arr.shape == trg_shape


@pytest.mark.parametrize(
    "bounds, trg_shape, geoid_ref_mean, ellipsoid_ref_mean",
    [
        ((-179.9, -79.2, -179.1, -79.1), (1, 362, 962), 44.088665, -9.830775),
        ((178.1, -79.2, 179.95, -79.1), (1, 362, 2222), 38.270348, -15.338912),
    ],
)
def test_remove_geoid(bounds, trg_shape, geoid_ref_mean, ellipsoid_ref_mean):
    os.makedirs(CURRENT_DIR / Path("TMP"), exist_ok=True)
    dem_tiles = find_required_dem_paths_from_index(
        bounds, cop30_index_path=TEST_COP30_INDEX_PATH
    )
    dem_arr, dem_profile = merge_raster_files(
        dem_tiles,
        output_path=CURRENT_DIR / Path("TMP") / Path("TMP.tif"),
        bounds=bounds,
        buffer_pixels=0,
    )
    dem_arr_ellipsoid = remove_geoid(
        dem_arr=dem_arr,
        dem_profile=dem_profile,
        geoid_path=TEST_GEOID_TIF_PATH,
        dem_area_or_point="Point",
        buffer_pixels=2,
        save_path="",
    )
    shutil.rmtree(CURRENT_DIR / Path("TMP"))
    assert dem_arr.shape == dem_arr_ellipsoid.shape
    assert dem_arr.shape == trg_shape
    assert np.mean(dem_arr) == pytest.approx(geoid_ref_mean, rel=1e-5)
    assert np.mean(dem_arr_ellipsoid) == pytest.approx(ellipsoid_ref_mean, rel=1e-5)


@pytest.mark.parametrize(
    "bounds, ellipsoid_heights, trg_shape, trg_crs",
    [
        ((-179.9, -79.2, -179.1, -79.1), False, (1, 366, 966), 4326),
        ((178.1, -79.2, 179.95, -79.1), False, (1, 366, 2226), 4326),
        (
            (-179.2, -79.2, 179.1, -79.1),
            False,
            (1, 1396, 1676),
            3031,
        ),  # across antimeridian
        (
            (-179.2, -79.2, 179.1, -79.1),
            True,
            (1, 1396, 1676),
            3031,
        ),  # across antimeridian
    ],
)
def test_get_cop30_dem_for_bounds(bounds, ellipsoid_heights, trg_shape, trg_crs):
    os.makedirs(CURRENT_DIR / Path("TMP"), exist_ok=True)
    dem_arr, dem_profile = get_cop30_dem_for_bounds(
        bounds,
        save_path=CURRENT_DIR / Path("TMP") / Path("TMP.tif"),
        ellipsoid_heights=ellipsoid_heights,
        buffer_pixels=2,
        cop30_index_path=TEST_COP30_INDEX_PATH,
        cop30_folder_path=TEST_COP30_FOLDER_PATH,
        geoid_tif_path=TEST_GEOID_TIF_PATH,
        adjust_for_high_lat_and_buffer=False,
    )
    # shutil.rmtree(CURRENT_DIR / Path('TMP'))
    assert dem_arr.shape == trg_shape
    assert dem_profile["crs"].to_epsg() == trg_crs


if __name__ == "__main__":

    os.makedirs(CURRENT_DIR / Path("TMP"), exist_ok=True)
    bounds = (-179.9, -79.2, -179.1, -79.1)
    dem_arr, dem_profile = get_cop30_dem_for_bounds(
        bounds,
        save_path=CURRENT_DIR / Path("TMP") / Path("TMP.tif"),
        ellipsoid_heights=True,
        buffer_pixels=0,
        cop30_index_path=TEST_COP30_INDEX_PATH,
        cop30_folder_path=TEST_COP30_FOLDER_PATH,
        geoid_tif_path=TEST_GEOID_TIF_PATH,
        adjust_for_high_lat_and_buffer=False,
    )
    print(dem_profile)
    empty_dem_profile = make_empty_cop30m_profile((0, -90, 1, -86))
    print(empty_dem_profile)
    dem_arr, dem_profile = expand_raster_to_bounds(
        bounds,
        src_profile=empty_dem_profile,
        fill_value=0,
        buffer_pixels=1,
        save_path=CURRENT_DIR / Path("TMP") / Path("EMPTY.tif"),
    )
    dem_bounds = bounds_from_profile(dem_profile)
    print(dem_profile)
