from dataclasses import dataclass
import pyproj
from shapely import segmentize
from shapely.geometry import Polygon, box
from pyproj.database import query_utm_crs_info
from pyproj.aoi import AreaOfInterest
from pyproj import CRS
import json
import logging

logger = logging.getLogger(__name__)


# Construct a dataclass for bounding boxes
@dataclass
class BoundingBox:
    xmin: float | int
    ymin: float | int
    xmax: float | int
    ymax: float | int

    @property
    def bounds(self) -> tuple[float | int, float | int, float | int, float | int]:
        return (self.xmin, self.ymin, self.xmax, self.ymax)

    @property
    def top_left(self) -> tuple[float | int, float | int]:
        return (self.xmin, self.ymax)

    @property
    def bottom_right(self) -> tuple[float | int, float | int]:
        return (self.xmax, self.ymin)

    # Run checks on the bounding box values
    def __post_init__(self):
        if self.ymin >= self.ymax:
            raise ValueError(
                "The bounding box's ymin value is greater than or equal to ymax value. Check ordering"
            )
        if self.xmin >= self.xmax:
            raise ValueError(
                "The bounding box's x_min value is greater than or equal to x_max value. Check ordering"
            )


def transform_polygon(
    geometry: Polygon, src_crs: int, dst_crs: int, always_xy: bool = True
):
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


def adjust_bounds(
    bounds: BoundingBox | tuple[float | int, float | int, float | int, float | int],
    src_crs: int,
    ref_crs: int,
    segment_length: float = 0.1,
) -> tuple:
    """_summary_

    Parameters
    ----------
    bounds : BoundingBox | tuple[float | int, float | int, float | int, float | int],
        Bounds to adjust.
    src_crs : int
        Source EPSG. e.g. 4326
    ref_crs : int
        Reference crs to create the true bbox. i.e. 3031 in southern
        hemisphere and 3995 in northern (polar stereographic)
    segment_length : float, optional
        distance between generation points along the bounding box sides in
        src_crs. e.g. 0.1 degrees in lat/lon, by default 0.1

    Returns
    -------
    BoundingBox
        A polygon bounding box expanded to the true min max
    """
    if isinstance(bounds, tuple):
        bounds = BoundingBox(*bounds)

    geometry = box(bounds.bounds)
    segmentized_geometry = segmentize(geometry, max_segment_length=segment_length)
    transformed_geometry = transform_polygon(segmentized_geometry, src_crs, ref_crs)
    transformed_box = box(*transformed_geometry.bounds)
    corrected_geometry = transform_polygon(transformed_box, ref_crs, src_crs)
    return BoundingBox(*corrected_geometry.bounds)


def get_local_utm(
    bounds: BoundingBox | tuple[float | int, float | int, float | int, float | int],
    antimeridian: bool = False,
) -> int:
    """_summary_

    Parameters
    ----------
    bounds : BoundingBox | tuple[float  |  int, float  |  int, float  |  int, float  |  int]
        The set of bounds (min_lon, min_lat, max_lon, max_lat)
    antimeridian : bool, optional
        Whether the bounds cross the antimerdian, by default False

    Returns
    -------
    int
        The CRS in integer form (e.g. 32749 for WGS 84 / UTM zone 49S)
    """
    if bounds.isinstance(tuple):
        bounds = BoundingBox(*bounds)

    logger.info("Finding best crs for area")
    centre_lat = (bounds.ymin + bounds.ymax) / 2
    centre_lon = (bounds.xmin + bounds.xmax) / 2
    if antimeridian:
        # force the lon to be next to antimeridian on the side with the scene centre.
        # e.g. (-177 + 178)/2 = 1, this is > 0 more data on -'ve side
        centre_lon = 179.9 if centre_lon < 0 else -179.9
    utm_crs_list = query_utm_crs_info(
        datum_name="WGS 84",
        area_of_interest=AreaOfInterest(
            west_lon_degree=centre_lon - 0.01,
            south_lat_degree=centre_lat - 0.01,
            east_lon_degree=centre_lon + 0.01,
            north_lat_degree=centre_lat + 0.01,
        ),
    )
    crs = CRS.from_epsg(utm_crs_list[0].code)
    crs = str(crs).split(":")[-1]  # get the EPSG integer
    return int(crs)


def bounds_to_geojson(bounds, save_path=""):
    """
    Convert a bounding box to a GeoJSON Polygon.

    Parameters:
        bounds (tuple): A tuple of (min_lon, min_lat, max_lon, max_lat).
        save_path (str): path to save the geojson

    Returns:
        dict: A GeoJSON FeatureCollection with a single Polygon feature.
    """
    min_lon, min_lat, max_lon, max_lat = bounds

    # Define the polygon coordinates
    coordinates = [
        [
            [min_lon, min_lat],
            [min_lon, max_lat],
            [max_lon, max_lat],
            [max_lon, min_lat],
            [min_lon, min_lat],  # Closing the polygon
        ]
    ]

    # Create the GeoJSON structure
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": coordinates},
                "properties": {},
            }
        ],
    }

    if save_path:
        with open(save_path, "w") as f:
            f.write(json.dumps(geojson))

    return geojson
