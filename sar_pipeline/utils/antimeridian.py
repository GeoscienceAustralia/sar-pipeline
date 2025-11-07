from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry import shape
from sar_pipeline.utils.spatial import get_all_lat_lon_coords
import antimeridian


class InvalidAntimeridianShapeError(ValueError):
    """Raised when the provided shape does not potentially cross the antimeridian
    as all coordinate points lie in either the eastern or western hemisphere"""

    pass


def check_shape_crosses_antimeridian(
    in_shape: Polygon | MultiPolygon, max_antimeridian_crossing_degrees: int = 20
) -> bool:
    """
    Determine whether a given shape crosses the antimeridian (±180° longitude).

    The function checks whether the provided geometry spans the antimeridian
    within a specified maximum angular width. For example, a shape with
    bounds `xmin=-176` and `xmax=170` spans 14° across the antimeridian,
    while the same bounds would span 346° if the antimeridian crossing were
    not considered.

    Depending on the data source or API, geometries crossing the antimeridian
    may be represented differently. For instance, both examples below describe
    Sentinel-1 scene footprints that cross the antimeridian:

    **Example (Polygon)**
        POLYGON ((
            178.576126 -71.618423, -178.032867 -70.167343,
            176.938004 -68.765106, 173.430893 -70.119957,
            178.576126 -71.618423
        ))

    **Example (MultiPolygon)**
        MULTIPOLYGON ((
            (
                178.576126 -71.618423, 180 -71.009119, 180 -69.618861,
                176.938004 -68.765106, 173.430893 -70.119957,
                178.576126 -71.618423
            ),
            (
                -180 -71.009119, -178.032867 -70.167343,
                -180 -69.618861, -180 -71.009119
            )
        ))

    Parameters
    ----------
    in_shape : shapely.Polygon or shapely.MultiPolygon
        The input geometry to test for an antimeridian crossing.
    max_antimeridian_crossing_degrees : int, optional
        Maximum allowable angular width (in degrees) across the antimeridian.
        Defaults to 20°.
    """

    longitudes, _ = get_all_lat_lon_coords(in_shape)

    west_longitudes = [x for x in longitudes if x < 0]
    east_longitudes = [x for x in longitudes if x > 0]

    if (not east_longitudes) or (not west_longitudes):
        # all points exist in either the eastern or western hemisphere."
        # therefore is not a potential antimeridian shape"
        return False

    # For a valid set of bounds that cross the antimeridian:
    # - max_west is the maximum negative longitude in the western hemisphere;
    # - min_east minimum positive longitude in the eastern hemisphere.
    max_west, min_east = max(west_longitudes), min(east_longitudes)

    # set our tolerances for an antimeridian crossing
    bounding_west = -180 + max_antimeridian_crossing_degrees  # -160 by default
    bounding_east = 180 - max_antimeridian_crossing_degrees  # 160 by default

    # check if the shape crosses the antimeridian within the allowable width
    if (max_west < bounding_west) and (min_east > bounding_east):
        # e.g. -170 < -160, 170 > 160
        return True
    else:
        # e.g. -5 > -160, 5 < 160 (normal meridian crossing)
        return False


def get_bounds_for_antimeridian_shape(in_shape: Polygon | MultiPolygon) -> tuple:
    """Get the correct set of bounds for a shape that crosses the antimeridian

    Parameters
    ----------
    in_shape : Polygon | MultiPolygon
        The input geometry that crosses the antimeridian.

    Returns
    -------
    tuple
        A tuple (left, bottom, right, top). Note, as the bounds cross
        The antimeridian, the left value is greater than the right
        e.g. (175, -65, -178, -60)

    Example
    ----------
    The Polygon and MultiPolygon are representations of the same shape.
    **Example (Polygon)**
        POLYGON ((
            178.576126 -71.618423, -178.032867 -70.167343,
            176.938004 -68.765106, 173.430893 -70.119957,
            178.576126 -71.618423
        ))
    **Example (MultiPolygon)**
        MULTIPOLYGON ((
            (
                178.576126 -71.618423, 180 -71.009119, 180 -69.618861,
                176.938004 -68.765106, 173.430893 -70.119957,
                178.576126 -71.618423
            ),
            (
                -180 -71.009119, -178.032867 -70.167343,
                -180 -69.618861, -180 -71.009119
            )
        ))

    get_bounds_for_antimeridian_shape(shape)
    >>> (173.430893, -71.618423, -178.032867, -68.765106)

    """
    longitudes, latitudes = get_all_lat_lon_coords(in_shape)

    west_longitudes = [x for x in longitudes if x < 0]
    east_longitudes = [x for x in longitudes if x > 0]

    if (not east_longitudes) or (not west_longitudes):
        raise InvalidAntimeridianShapeError(
            "Provided shape exists fully in either the eastern or western hemisphere and therefore"
            "cannot be a valid antimeridian shape. Shape must have points on both sides of 180° longitude. "
            f"Provided shape : {in_shape}"
        )

    # For a valid set of bounds that cross the antimeridian, left > right:
    # - right is the maximum negative longitude in the western hemisphere;
    # - left minimum positive longitude in the eastern hemisphere.
    right, left = max(west_longitudes), min(east_longitudes)
    bottom, top = min(latitudes), max(latitudes)

    return (left, bottom, right, top)


def convert_antimeridian_polygon_to_multipolygon(
    in_shape: Polygon,
) -> MultiPolygon:
    """The correct way to represent a geometry crossing the antimeridian is by
    using a MultiPolygon. The MultiPolygon consists of valid Polygons either
    side of the antimeridian. The function accepts a geometry crossing the
    antimeridian and returns the associated MultiPolygon. Note, if a valid
    MultiPolygon is provided, no changes will be made.

    Parameters
    ----------
    in_shape : Polygon | MultiPolygon
        The input geometry that crosses the antimeridian.

    Returns
    -------
    MultiPolygon
        A valid multipolygon with Polygons either side if the antimeridian
    """

    if not isinstance(in_shape, Polygon):
        raise TypeError("Input shape must be a shapely Polygon")

    longitudes, _ = get_all_lat_lon_coords(in_shape)

    west_longitudes = [x for x in longitudes if x < 0]
    east_longitudes = [x for x in longitudes if x > 0]

    if (not east_longitudes) or (not west_longitudes):
        raise InvalidAntimeridianShapeError(
            "Provided shape exists fully in either the eastern or western hemisphere and therefore"
            "cannot be a valid antimeridian shape. Shape must have points on both sides of 180° longitude. "
            f"Provided shape : {in_shape}"
        )

    # fix using the antimeridian package - https://www.gadom.ski/antimeridian/latest/
    # maintains shapes across the AM
    fixed_shape_dict = antimeridian.fix_shape(in_shape)
    fixed_shape = shape(fixed_shape_dict)
    return fixed_shape
