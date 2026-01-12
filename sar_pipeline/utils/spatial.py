import pyproj
from pyproj import Transformer
from shapely import wkt
from shapely.geometry import mapping, box, Polygon, shape, MultiPolygon
from shapely import segmentize
from shapely.ops import unary_union, orient
import numpy as np
import rasterio
from rasterio.features import shapes
import json
from pathlib import Path
import requests
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


def load_burst_geometry_from_geojson(geojson_path: Path, burst_id: str):
    """
    Load the geometry for a given burst_id from a GeoJSON file.

    Parameters
    ----------
    geojson_path : Path
        Path to the GeoJSON file written by write_burst_geometries_to_geojson.
    burst_id : str
        The burst identifier to look up.

    Returns
    -------
    shapely.geometry.BaseGeometry
        The geometry for the requested burst_id.

    Raises
    ------
    KeyError
        If the burst_id is not found in the file.
    """
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for feature in data["features"]:
        if feature["properties"].get("burst_id") == burst_id:
            return shape(feature["geometry"])

    raise KeyError(f"Burst ID {burst_id} not found in {geojson_path}")


def get_valid_data_min_rect_polygon_from_tif(
    tif_path: Path,
    n_segments: int = 4,
) -> Polygon:
    """
    Extract an approximate (rotated) rectangular boundary polygon
    around valid (non-nodata) data in a GeoTIFF, ignoring NoData areas.
    Additional segments are added to the polygon based on the n_segments
    setting. This ensures that re-projections are handled correctly, as these
    can be problematic using a simple rectangle as the shape is not preserved.

    Parameters
    ----------
    tif_path : Path
        Path to the GeoTIFF file.
    n_segments : int, optional
        The number of segments/points to add along each side of the
        minimum bounding rectangle.

    Returns
    -------
    shapely.geometry.Polygon or None
        Polygon representing the outer boundary of valid data.
        Returns None if no valid pixels are found.
    """
    with rasterio.open(tif_path) as ds:
        data = ds.read(1)
        nodata = ds.nodata

        # Build mask where True = valid data
        if nodata is None:
            # No explicit nodata, assume NaNs mark invalid
            mask = ~np.isnan(data)
        elif np.isnan(nodata):
            # nodata is NaN
            mask = ~np.isnan(data)
        else:
            # normal numeric nodata value
            mask = data != nodata

        if not np.any(mask):
            return None

        # Extract shapes of valid data
        results = (
            {"properties": {"val": v}, "geometry": s}
            for i, (s, v) in enumerate(
                shapes(mask.astype(np.uint8), mask=mask, transform=ds.transform)
            )
            if v == 1
        )

        polys = [shape(feat["geometry"]) for feat in results]
        if not polys:
            return None

        # merge the polygons
        merged = unary_union(polys)
        if isinstance(merged, MultiPolygon):
            merged = unary_union(merged)

        # Approximate with minimum rotated rectangle
        rect = merged.minimum_rotated_rectangle

        # Ensure consistent orientation (CCW)
        rect = orient(rect, sign=1.0)

        if n_segments:
            coords = np.array(rect.exterior.coords)
            # Compute pairwise edge lengths
            edge_lengths = np.sqrt(np.sum(np.diff(coords, axis=0) ** 2, axis=1))
            segment_length = np.min(edge_lengths) / n_segments
            segmentized_geometry = segmentize(rect, max_segment_length=segment_length)
            return segmentized_geometry
        else:
            return rect


def get_all_lon_lat_coords(
    geom: Polygon | MultiPolygon,
) -> tuple[list, list]:
    """
    Extract all longitude (x) and latitude (y) coordinates from a Shapely Polygon or MultiPolygon.
    This function gathers coordinates from both the exterior boundary and any interior rings
    (holes) of each polygon in the input geometry.

    Parameters
    ----------
    geom : Polygon or MultiPolygon
        The input geometry to extract coordinates from.

    Returns
    -------
    tuple(longitudes, latitudes)

    longitudes : list
        list of x-coordinates (longitude values).
    latitudes : list
        list array of y-coordinates (latitude values).

    Raises
    ------
    TypeError
        If the input geometry is not a Polygon or MultiPolygon.
    """

    def coords_from_polygon(polygon):
        exterior = list(polygon.exterior.coords)
        interiors = [pt for interior in polygon.interiors for pt in interior.coords]
        return exterior + interiors

    if isinstance(geom, Polygon):
        coords = coords_from_polygon(geom)
    elif isinstance(geom, MultiPolygon):
        coords = [pt for poly in geom.geoms for pt in coords_from_polygon(poly)]
    else:
        raise TypeError("Geometry must be a Polygon or MultiPolygon")

    longitudes, latitudes = zip(*coords) if coords else ([], [])
    return list(longitudes), list(latitudes)


def write_shape_to_geojson(
    in_shape: Polygon | MultiPolygon, filename: str | Path, indent=True
):
    """save a shape to a file

    Parameters
    ----------
    in_shape : Polygon | MultiPolygon
        Shape to save
    filename : str | Path
        file save location
    """

    # Convert to GeoJSON-like dict
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(in_shape),  # or mapping(multi_poly)
                "properties": {"name": f"{Path(filename).name}"},
            }
        ],
    }

    # Write to file
    with open(f"{filename}", "w") as f:
        if indent:
            json.dump(geojson, f, indent=4)
        else:
            json.dump(geojson, f)


def load_geojson_as_multipolygon(shape_path: str) -> MultiPolygon:
    """
    Load a GeoJSON from a URL (or local file) and return a flattened
    MultiPolygon.

    Handles GeoJSONs containing:
    - Polygon features
    - MultiPolygon features
    - Mix of both

    Parameters
    ----------
    url : str
        URL or local path to the GeoJSON.

    Returns
    -------
    MultiPolygon
        Flattened MultiPolygon containing all polygons from the GeoJSON.
    """

    logger.info(f"Loading geojson into shape : {shape_path}")

    # Load GeoJSON (supports URL or local file)
    if shape_path.startswith("http://") or shape_path.startswith("https://"):
        resp = requests.get(shape_path)
        resp.raise_for_status()
        geojson = resp.json()
    else:
        import json

        with open(shape_path, "r") as f:
            geojson = json.load(f)

    # Collect all geometries
    geometries = []

    features = geojson.get("features", [])
    for feat in features:
        geom = shape(feat["geometry"])
        if isinstance(geom, Polygon):
            geometries.append(geom)
        elif isinstance(geom, MultiPolygon):
            geometries.extend(geom.geoms)
        else:
            raise ValueError(f"Unexpected geometry type: {type(geom)}")

    if not geometries:
        raise ValueError("No Polygon/MultiPolygon geometries found in GeoJSON.")

    # Return a single flattened MultiPolygon
    return MultiPolygon(geometries)
