from pyproj import Transformer

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
    polygon_str = polygon_str.replace("POLYGON ((", "").replace("))", "")
    coordinates = [list(map(float, coord.split())) for coord in polygon_str.split(", ")]
    geojson = {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coordinates]},
    }
    return geojson

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