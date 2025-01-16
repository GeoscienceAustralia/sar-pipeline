import pyproj
from shapely import segmentize
from shapely.geometry import Polygon, box


def transform_polygon(
    geometry: Polygon, src_crs: int, dst_crs: int, always_xy: bool = True
):
    src_crs = pyproj.CRS(f"EPSG:{src_crs}")
    dst_crs = pyproj.CRS(f"EPSG:{dst_crs}")
    transformer = pyproj.Transformer.from_crs(src_crs, dst_crs, always_xy=always_xy)
    # Transform the polygon's coordinates
    transformed_exterior = [
        transformer.transform(x, y) for x, y in geometry.exterior.coords
    ]
    # Create a new Shapely polygon with the transformed coordinates
    transformed_polygon = Polygon(transformed_exterior)
    return transformed_polygon


def transform_scene_extent(
    geometry: Polygon, src_crs: int, ref_crs: int, segment_length: float = 0.1
) -> Polygon:
    """
    Adjust the bounding box around a scene in src_crs (4326) due to warping at high
    Latitudes. For example, the min and max boudning values for an antarctic scene in
    4326 may not actually be the true min and max due to distortions at high latitudes.

    Parameters:
    - geometry: Polygon of the scene geometry.
    - src_crs: Source EPSG. e.g. 4326
    - ref_crs: reference crs to create the true bbox. i.e. 3031 in southern
                hemisphere and 3995 in northern (polar stereographic)
    - segment_length: distance between generation points along the bounding box sides in
            src_crs. e.g. 0.1 degrees in lat/lon

    Returns:
    - A polygon bounding box expanded to the true min max
    """

    segmentized_geometry = segmentize(geometry, max_segment_length=segment_length)

    transformed_geometry = transform_polygon(segmentized_geometry, src_crs, ref_crs)
    transformed_box = box(*transformed_geometry.bounds)

    corrected_geometry = transform_polygon(transformed_box, ref_crs, src_crs)

    return corrected_geometry
