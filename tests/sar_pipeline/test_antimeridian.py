import pytest
from dataclasses import dataclass
import shapely
from shapely.geometry import Polygon, MultiPolygon
from sar_pipeline.utils.spatial import write_shape_to_geojson
from sar_pipeline.utils.antimeridian import (
    check_shape_crosses_antimeridian,
    get_bounds_for_antimeridian_shape,
    convert_antimeridian_polygon_to_multipolygon,
)


@dataclass
class CheckCrossAM:
    test_name: str
    in_shape: Polygon | MultiPolygon
    bounds: tuple
    max_antimeridian_crossing_degrees: float
    crosses_AM: bool
    in_shape_fixed: MultiPolygon | None


# ===== Define input geometries for testing =====

# crosses the AM
in_shape_1 = Polygon(
    [
        (178.576126, -71.618423),
        (-178.032867, -70.167343),
        (176.938004, -68.765106),
        (173.430893, -70.119957),
        (178.576126, -71.618423),
    ],
)  # actual s1 iw scene

# crosses the AM
in_shape_2 = Polygon(
    [
        (179.5, -10.0),  # Just west of the antimeridian
        (-179.8, -10.0),  # Just east of the antimeridian
        (-178.5, 15.0),  # Further east
        (178.0, 12.0),  # West again
        (179.5, -10.0),  # Close the ring
    ]
)

# crosses the AM
in_shape_3 = Polygon(
    [
        (170.0, -55.0),  # Western point
        (-175.0, -55.0),  # Just east of antimeridian
        (-160.0, -45.0),  # Farther east
        (175.0, -45.0),  # Back west
        (170.0, -55.0),  # Close the loop
    ]
)

# crosses the AM
in_shape_4 = MultiPolygon([in_shape_1, in_shape_2])

# polygon on the regular meridian
in_shape_5 = Polygon(
    [
        (-2.5, -5.0),  # Southwest corner
        (2.5, -5.0),  # Southeast corner
        (2.5, 5.0),  # Northeast corner
        (-2.5, 5.0),  # Northwest corner
        (-2.5, -5.0),  # Close the ring
    ]
)

# Polygon fully in the western hemisphere (centered around -5° longitude, 5° wide)
in_shape_6 = Polygon(
    [
        (-7.5, -5.0),  # Southwest corner
        (-2.5, -5.0),  # Southeast corner
        (-2.5, 5.0),  # Northeast corner
        (-7.5, 5.0),  # Northwest corner
        (-7.5, -5.0),  # Close the ring
    ]
)

# IW scene crossing AM (shape from CDSE API)
# S1A_IW_SLC__1SSH_20250307T153618_20250307T153648_058200_0730F9_4BB9
in_shape_7a = shapely.from_wkt(
    "MULTIPOLYGON ("
    "((178.573151 -71.619789, 180 -71.009304, 180 -69.621165, 176.934128 -68.766289, 173.42691 -70.120949, 178.573151 -71.619789)), "
    "((-180 -71.009304, -178.035721 -70.168877, -180 -69.621165, -180 -71.009304))"
    ")"
)

# IW scene crossing AM (shape from ASF API)
# S1A_IW_SLC__1SSH_20250307T153618_20250307T153648_058200_0730F9_4BB9
in_shape_7b = shapely.from_wkt(
    "POLYGON ("
    "(-178.035721 -70.168877, 176.934128 -68.766289, 173.42691 -70.120949, 178.573151 -71.619789, -178.035721 -70.168877)"
    ")"
)

# ===== Define the correct bounds for AM geometries =====

# the bounds corresponding to the shapes
b1 = (173.430893, -71.618423, -178.032867, -68.765106)
b2 = (178.0, -10, -178.5, 15)
b3 = (170, -55, -160, -45)
b4 = (173.430893, -71.618423, -178.032867, 15)
b5 = (-2.5, -5, 2.5, 5)
b6 = (-7.5, -5, -2.5, 5)
b7 = (173.42691, -71.619789, -178.035721, -68.766289)

# ===== Define the fixed geometries when correctly split at the AM =====

# create the desired shapes when split along the AM
in_shape_fixed_1_east = Polygon(
    [
        [180.0, -69.657589],
        [176.93800399999998, -68.765106],
        [173.43089299999997, -70.119957],
        [178.576126, -71.618423],
        [180.0, -71.0422975],
        [180.0, -69.657589],
    ]
)
in_shape_fixed_1_west = Polygon(
    [
        [-180.0, -71.0422975],
        [-178.032867, -70.167343],
        [-180.0, -69.657589],
        [-180.0, -71.0422975],
    ]
)
in_shape_fixed_1 = MultiPolygon([in_shape_fixed_1_east, in_shape_fixed_1_west])

in_shape_fixed_2_east = Polygon(
    [
        [180.0, 13.7295355],
        [178.0, 12.0],
        [179.5, -10.0],
        [180.0, -10.0001492],
        [180.0, 13.7295355],
    ]
)
in_shape_fixed_2_west = Polygon(
    [
        [-180.0, -10.0001492],
        [-179.8, -10.0],
        [-178.5, 15.0],
        [-180.0, 13.7295355],
        [-180.0, -10.0001492],
    ]
)
in_shape_fixed_2 = MultiPolygon([in_shape_fixed_2_east, in_shape_fixed_2_west])

in_shape_fixed_3_east = Polygon(
    [
        [180.0, -45.4410887],
        [175.0, -45.0],
        [170.0, -55.0],
        [180.0, -55.2053924],
        [180.0, -45.4410887],
    ]
)
in_shape_fixed_3_west = Polygon(
    [
        [-180.0, -55.2053924],
        [-175.0, -55.0],
        [-160.0, -45.0],
        [-180.0, -45.4410887],
        [-180.0, -55.2053924],
    ]
)
in_shape_fixed_3 = MultiPolygon([in_shape_fixed_3_east, in_shape_fixed_3_west])

# note the fixed MultiPolygon for test 7b is very slightly different
# from the in_shape_7a MultiPolygon, (a result of attempting to reconstruct
# the valid MultiPolygon from the input Polygon)
in_shape_fixed_7b_east = Polygon(
    [
        [-180.0, -71.0425001],
        [-178.035721, -70.168877],
        [-180.0, -69.6598863],
        [-180.0, -71.0425001],
    ]
)
in_shape_fixed_7b_west = Polygon(
    [
        [180.0, -69.6598863],
        [176.934128, -68.766289],
        [173.42691000000002, -70.120949],
        [178.573151, -71.619789],
        [180.0, -71.0425001],
        [180.0, -69.6598863],
    ]
)
in_shape_fixed_7b = MultiPolygon([in_shape_fixed_7b_east, in_shape_fixed_7b_west])

test_1a = CheckCrossAM(
    test_name="test_1a",
    in_shape=in_shape_1,
    bounds=b1,
    max_antimeridian_crossing_degrees=20,
    crosses_AM=True,
    in_shape_fixed=in_shape_fixed_1,
)
test_1b = CheckCrossAM(
    test_name="test_1b",
    in_shape=in_shape_1,
    bounds=b1,
    max_antimeridian_crossing_degrees=1,
    crosses_AM=False,  # max_antimeridian_crossing_degrees not big enough,
    in_shape_fixed=False,
)

test_2 = CheckCrossAM(
    test_name="test_2",
    in_shape=in_shape_2,
    bounds=b2,
    max_antimeridian_crossing_degrees=20,
    crosses_AM=True,
    in_shape_fixed=in_shape_fixed_2,
)
test_3a = CheckCrossAM(
    test_name="test_3a",
    in_shape=in_shape_3,
    bounds=b3,
    max_antimeridian_crossing_degrees=20,
    crosses_AM=False,  # max_antimeridian_crossing_degrees not big enough,
    in_shape_fixed=None,
)
test_3b = CheckCrossAM(
    test_name="test_3b",
    in_shape=in_shape_3,
    bounds=b3,
    max_antimeridian_crossing_degrees=35,
    crosses_AM=True,
    in_shape_fixed=in_shape_fixed_3,
)
test_4 = CheckCrossAM(
    test_name="test_4",
    in_shape=in_shape_4,
    bounds=b4,
    max_antimeridian_crossing_degrees=20,
    crosses_AM=True,
    in_shape_fixed=None,  # Already MultiPolygon
)
test_5 = CheckCrossAM(
    test_name="test_5",
    in_shape=in_shape_5,
    bounds=b5,
    max_antimeridian_crossing_degrees=20,
    crosses_AM=False,
    in_shape_fixed=None,
)
test_6 = CheckCrossAM(
    test_name="test_6",
    in_shape=in_shape_6,
    bounds=b6,
    max_antimeridian_crossing_degrees=20,
    crosses_AM=False,
    in_shape_fixed=None,
)
test_7a = CheckCrossAM(
    test_name="test_7a",
    in_shape=in_shape_7a,
    bounds=b7,
    max_antimeridian_crossing_degrees=20,
    crosses_AM=True,
    in_shape_fixed=None,  # Already MultiPolygon
)

test_7b = CheckCrossAM(
    test_name="test_7b",
    in_shape=in_shape_7b,
    bounds=b7,
    max_antimeridian_crossing_degrees=20,
    crosses_AM=True,
    in_shape_fixed=in_shape_fixed_7b,
)


# Combine for parameterization
test_cases = [
    test_1a,
    test_1b,
    test_2,
    test_3a,
    test_3b,
    test_4,
    test_5,
    test_6,
    test_7a,
    test_7b,
]


@pytest.mark.parametrize("test_case", test_cases)
def test_check_shape_crosses_antimeridian(test_case):
    # assert the correct shapes get flagged as crossing the AM
    shape_crosses_AM = check_shape_crosses_antimeridian(
        test_case.in_shape, test_case.max_antimeridian_crossing_degrees
    )
    assert shape_crosses_AM == test_case.crosses_AM


@pytest.mark.parametrize("test_case", test_cases)
def test_get_bounds_for_antimeridian_shape(test_case):
    # assert the bounds are correctly extracted from the shapes
    if test_case.crosses_AM:
        am_bounds = get_bounds_for_antimeridian_shape(test_case.in_shape)
        assert am_bounds == test_case.bounds


@pytest.mark.parametrize("test_case", test_cases)
def test_get_multipolygon_from_antimeridian_shape(test_case):
    # assert the bounds are correctly extracted from the shapes
    if test_case.crosses_AM and isinstance(test_case.in_shape, Polygon):
        fixed_shape = convert_antimeridian_polygon_to_multipolygon(test_case.in_shape)
        # write the fixed shape to a local file
        # write_shape_to_geojson(fixed_shape, f"{test_case.test_name}_fixed.json")
        assert fixed_shape == test_case.in_shape_fixed
