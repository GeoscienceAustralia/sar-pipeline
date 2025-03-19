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
    polygon_str = polygon_str.replace('POLYGON ((', '').replace('))', '')
    coordinates = [list(map(float, coord.split())) for coord in polygon_str.split(', ')]
    geojson = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [coordinates]
        },
    }
    return geojson