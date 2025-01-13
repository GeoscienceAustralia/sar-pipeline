from sar_antarctica.nci.preparation.dem import (
    check_s1_bounds_cross_antimeridian,
    split_s1_bounds_at_am_crossing,
    get_target_antimeridian_projection,
    make_empty_cop30m_profile

) 
import shapely
import pytest
import math

from data.cop30m_profile import TEST_COP30_PROFILE_1, TEST_COP30_PROFILE_2

def test_pytest():
    assert True

@pytest.mark.parametrize("bounds, expected", [
    ((163.121597, -78.632782, 172.382263, -76.383263), False),  # Bounds that do not cross the antimeridian
    ((170, -70, 180, -76), False),  # Bounds that do not cross the antimeridian
    ((-180, 10, -175, 20), False),  # Bounds that do not cross the antimeridian
    ((-177.884048, -78.176201, 178.838364, -75.697151), True),  # Bounds that cross the antimeridian
])
def test_check_s1_bounds_cross_antimeridian(bounds, expected):
    assert check_s1_bounds_cross_antimeridian(bounds) == expected

@pytest.mark.parametrize("bounds, lat_buff, expected_left, expected_right", [
    ((-177.884048, -78.176201, 178.838364, -75.697151), 0, (-180, -78.176201, -177.884048, -75.697151), (178.838364, -78.176201, 180, -75.697151)), 
    ((-177.884048, -78.176201, 178.838364, -75.697151), 0.1, (-180, -78.276201, -177.884048, -75.597151), (178.838364, -78.276201, 180, -75.597151)),  
])
def test_split_bounds_at_am_crossing(bounds, lat_buff, expected_left, expected_right):
    left, right = split_s1_bounds_at_am_crossing(bounds, lat_buff)
    # use pytest.approx to get around small rounding errors with floats
    assert all(a == pytest.approx(b,rel=1e-9) for a, b in zip(left, expected_left))
    assert all(a == pytest.approx(b,rel=1e-9) for a, b in zip(right, expected_right)) 

@pytest.mark.parametrize("bounds, target_crs", [
    ((-177.884048, -78.176201, 178.838364, -75.697151), 3031), # antarctic
    ((-177.884048, 78.176201, 178.838364, 75.697151), 3995), # arctic
    ((-177.884048, -1, 178.838364, 1), 32601), # centre slight left of equator
    ((-178.884048, -1, 177.838364, 1), 32660), # centre slight right of equator
])
def test_get_target_antimeridian_projection(bounds, target_crs):
    assert get_target_antimeridian_projection(bounds) == target_crs

@pytest.mark.parametrize("bounds_to_profile", [
    TEST_COP30_PROFILE_1,
    TEST_COP30_PROFILE_2
    ])
def test_make_empty_cop30m_profile(bounds_to_profile):
    bounds, target_profile = bounds_to_profile
    profile = make_empty_cop30m_profile(bounds)
    for key in profile.keys():
        if isinstance(profile[key], float) and math.isnan(profile[key]) and isinstance(target_profile[key], float) and math.isnan(target_profile[key]):
            # Handle NaN comparison
            continue
        assert profile[key] == target_profile[key]

if __name__ == "__main__":

    from sar_antarctica.nci.preparation.dem import (
        get_cop30_dem_for_bounds,
        find_required_dem_tile_paths_by_filename,
        find_required_dem_paths_from_geopackage
    )

    import logging
    logging.basicConfig()
    logging.getLogger().setLevel(logging.INFO)
    from shapely.geometry import box
    import geopandas as gpd
    
    # bounds = (163.121597, -78.632782, 172.382263, -76.383263) # full s1 scene
    #bounds = (165, -76.632782, 170, -75) # smaller area
    # bounds = (-177.884048, -78.176201, 178.838364, -75.697151) # full AM scene bounds
    # bounds = (-177.2, -79.2, 178.1, -77.1) # smaller AM bounds
    bounds = (140, -66, 141, -65) # smaller area over water
    # bounds = (20.1, -75.2, 22.2, -73.1) 
    # bounds = (-22.2, -75.2, -20.1, -73.1) 


    dem_paths = find_required_dem_paths_from_geopackage(bounds)
    print(f'{len(dem_paths)} tiles found')
    print(dem_paths)
    dem_paths = find_required_dem_tile_paths_by_filename(bounds)
    print(f'{len(dem_paths)} tiles found')
    print(dem_paths)
    get_cop30_dem_for_bounds(bounds, ellipsoid_heights=True, save_path='dem_tmp.tif')
    #profile = make_empty_cop30m_profile((0, -90, 1, -86))

    # save bounds for exploration
    gdf = gpd.GeoDataFrame([{"geometry": box(*bounds)}], crs="EPSG:4326")
    # Write the GeoDataFrame to a GeoJSON file
    gdf.to_file("bounding_box.geojson", driver="GeoJSON")