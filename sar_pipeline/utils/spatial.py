import pyproj
from pyproj import Transformer
from shapely import wkt
from shapely.geometry import mapping, box, Polygon
from shapely import segmentize
import json
from pathlib import Path
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def polygon_str_to_geojson(polygon_str: str) -> dict:
    """convert polygon string to a geojson

    Parameters
    ----------
    polygon_str : str
        polygon string

    Returns
    -------
    dict
        Geojson for the polygon
    """
    # Load and convert
    geometry = wkt.loads(polygon_str)
    geojson_feature = mapping(geometry)
    return geojson_feature


def convert_bbox(bbox, src_crs, trg_crs):
    """
    Convert a bounding box from one CRS to another.

    Parameters:
        bbox (tuple): Bounding box as (min_x, min_y, max_x, max_y).
        src_crs (str or int): Source coordinate reference system (EPSG code or proj string).
        trg_crs (str or int): Target coordinate reference system (EPSG code or proj string).

    Returns:
        tuple: Transformed bounding box (min_x, min_y, max_x, max_y).
    """
    transformer = Transformer.from_crs(src_crs, trg_crs, always_xy=True)

    # Transform all four corners
    x1, y1 = transformer.transform(bbox[0], bbox[1])
    x2, y2 = transformer.transform(bbox[2], bbox[1])
    x3, y3 = transformer.transform(bbox[2], bbox[3])
    x4, y4 = transformer.transform(bbox[0], bbox[3])

    # Compute new bounding box
    min_x = min(x1, x2, x3, x4)
    max_x = max(x1, x2, x3, x4)
    min_y = min(y1, y2, y3, y4)
    max_y = max(y1, y2, y3, y4)

    return min_x, min_y, max_x, max_y


def transform_polygon(
    geometry: Polygon, src_crs: int, trg_crs: int, always_xy: bool = True
):
    """point by point reprojection of a polygon

    Parameters
    ----------
    geometry : Polygon
        input geometry
    src_crs : int
        the source CRS
    trg_crs : int
        the target CRS
    always_xy : bool, optional
        Points are given in x,y, by default True

    Returns
    -------
    shapely.Polygon
        The transformed shape.

    Raises
    ------
    ValueError
        Shape error, not a Polygon
    """
    src_crs = pyproj.CRS(f"EPSG:{src_crs}")
    trg_crs = pyproj.CRS(f"EPSG:{trg_crs}")
    transformer = pyproj.Transformer.from_crs(src_crs, trg_crs, always_xy=always_xy)
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


def reproject_bbox_to_geometry(
    bbox: list | tuple,
    src_crs: int,
    trg_crs: int,
    n_segments: int = 5,
):
    """Segments a bounding box and reprojects from one CRS to another. This ensures that
    the 'box' shape is maintained in the new crs. For example, a box in 4326 is converted
    to a geometry in 3031 that maintains the 4326 box shape/tilt.

    Parameters
    ----------
    bbox : list | tuple
        Bounding box as (min_x, min_y, max_x, max_y).
    src_crs : int
        The EPSG code of the input bbox
    trg_crs : int
        The target EPSG code of the output geometry
    n_segments : float, optional
        Minimum number of segments along each edge

    Returns
    -------
    shapely:geometry
        A polygon in the shape of the input bbox in a new projection
    """

    bbox_geometry = box(*bbox)
    segment_length = min(abs(bbox[0] - bbox[2]), abs(bbox[1] - bbox[3])) / n_segments
    segmentized_geometry = segmentize(bbox_geometry, max_segment_length=segment_length)
    transformed_geometry = transform_polygon(segmentized_geometry, src_crs, trg_crs)
    return transformed_geometry


def write_burst_geometries_to_geojson(burst_id_list, burst_geometry_list, save_path):
    """
    Write burst geometries and their IDs to a GeoJSON file.

    Parameters
    ----------
    burst_id_list : list of str
        List of burst identifiers (e.g., "t007_014545_iw2").
    burst_geometry_list : list of shapely.geometry.BaseGeometry
        List of corresponding geometries for each burst ID. Must be in the same order as `burst_id_list`.
    save_path : str or Path
        Path to save the resulting GeoJSON file. Will be overwritten if it exists.

    Raises
    ------
    ValueError
        If `burst_id_list` and `burst_geometry_list` have different lengths.

    """
    if len(burst_id_list) != len(burst_geometry_list):
        raise ValueError(
            "burst_id_list and burst_geometry_list must have the same length."
        )

    features = []
    for burst_id, geom in zip(burst_id_list, burst_geometry_list):
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {"burst_id": burst_id},
            }
        )

    geojson_obj = {"type": "FeatureCollection", "features": features}

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(geojson_obj, f, indent=2)
