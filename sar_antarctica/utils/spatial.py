import pyproj
from shapely import segmentize
from shapely.geometry import Polygon, box
from pyproj.database import query_utm_crs_info
from pyproj.aoi import AreaOfInterest
from pyproj import CRS
import logging

def transform_polygon(geometry: Polygon, src_crs: int, dst_crs: int, always_xy: bool = True):
    src_crs = pyproj.CRS(f"EPSG:{src_crs}")
    dst_crs = pyproj.CRS(f"EPSG:{dst_crs}") 
    transformer = pyproj.Transformer.from_crs(src_crs, dst_crs, always_xy=always_xy)
     # Transform the polygon's coordinates
    if isinstance(geometry, Polygon):
        # Transform exterior
        exterior_coords = [
            transformer.transform(x, y) for x, y in geometry.exterior.coords
        ]
        # Transform interiors (holes)
        interiors_coords = [
            [transformer.transform(x, y) for x, y in interior.coords]
            for interior in geometry.interiors
        ]
        # Create the transformed polygon
        return Polygon(exterior_coords, interiors_coords)

    # Handle other geometry types as needed
    raise ValueError("Only Polygon geometries are supported for transformation.")

def adjust_bounds(bounds: tuple, src_crs: int, ref_crs: int, segment_length: float = 0.1) -> tuple:
    """
    Adjust the bounding box around a scene in src_crs (4326) due to warping at high
    Latitudes. For example, the min and max boudning values for an antarctic scene in
    4326 may not actually be the true min and max due to distortions at high latitudes. 

    Parameters:
    - bounds: bounds to adjust.
    - src_crs: Source EPSG. e.g. 4326
    - ref_crs: reference crs to create the true bbox. i.e. 3031 in southern 
                hemisphere and 3995 in northern (polar stereographic)
    - segment_length: distance between generation points along the bounding box sides in
            src_crs. e.g. 0.1 degrees in lat/lon 

    Returns:
    - A polygon bounding box expanded to the true min max
    """

    geometry = box(*bounds)
    segmentized_geometry = segmentize(geometry, max_segment_length=segment_length)
    transformed_geometry = transform_polygon(segmentized_geometry, src_crs, ref_crs)
    transformed_box = box(*transformed_geometry.bounds)
    corrected_geometry = transform_polygon(transformed_box, ref_crs, src_crs)
    return tuple(corrected_geometry.bounds)


def get_local_utm(bounds, antimeridian=False):
    centre_lat = (bounds[1] + bounds[3])/2
    centre_lon = (bounds[0] + bounds[2])/2
    if antimeridian:
        # force the lon to be next to antimeridian on the side with the scene centre.
        # e.g. (-177 + 178)/2 = 1, this is > 0 more data on -'ve side
        centre_lon = 179.9 if centre_lon < 0 else -179.9
    utm_crs_list = query_utm_crs_info(
        datum_name="WGS 84",
        area_of_interest=AreaOfInterest(
            west_lon_degree=centre_lon-0.01,
            south_lat_degree=centre_lat-0.01,
            east_lon_degree=centre_lon+0.01,
            north_lat_degree=centre_lat+0.01,
        ),
    )
    crs = CRS.from_epsg(utm_crs_list[0].code)
    crs = str(crs).split(':')[-1] # get the EPSG integer
    return int(crs)
