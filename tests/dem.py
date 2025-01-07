from sar_antarctica.nci.preparation.dem import (
    check_s1_bounds_cross_antimeridian,
    split_s1_bounds_at_am_crossing
) 
import shapely
import pytest

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
    ((-177.884048, -78.176201, 178.838364, -75.697151), 0, (-180, -78.176201, -177.884048, -75.697151), (-177.884048, -78.176201, 180, -75.697151)), 
    ((-177.884048, -78.176201, 178.838364, -75.697151), 0.1, (-180, -78.276201, -177.884048, -75.597151), (-177.884048, -78.276201, 180, -75.597151)),  
])
def test_split_bounds_at_am_crossing(bounds, lat_buff, expected_left, expected_right):
    left, right = split_s1_bounds_at_am_crossing(bounds, lat_buff)
    # use pytest.approx to get around small rounding errors with floats
    assert all(a == pytest.approx(b,rel=1e-9) for a, b in zip(left, expected_left))
    assert all(a == pytest.approx(b,rel=1e-9) for a, b in zip(right, expected_right)) 


if __name__ == "__main__":

    from sar_antarctica.nci.preparation.dem import (
        get_cop30_dem_for_bounds,
        find_required_dem_tile_paths
    )

    import logging
    logging.basicConfig()
    logging.getLogger().setLevel(logging.INFO)
    
    # bounds = (163.121597, -78.632782, 172.382263, -76.383263) # full s1 scene
    bounds = (165, -76.632782, 170, -75) # smaller area
    #bounds = (-177.884048, -78.176201, 178.838364, -75.697151) # full AM scene bounds
    #bounds = (-179, -78, 179, -77) # smaller AM bounds

    #dem_paths = find_required_dem_tile_paths(bounds)
    #print(f'{len(dem_paths)} tiles found')
    get_cop30_dem_for_bounds(bounds, save_path='dem_tmp.tif')