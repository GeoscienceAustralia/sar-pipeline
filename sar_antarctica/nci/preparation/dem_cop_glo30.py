from affine import Affine
import math
import numpy as np
from rasterio.crs import CRS
from sar_antarctica.utils.raster import (
    adjust_pixel_coordinate_from_point_to_area,
    expand_bounding_box_to_pixel_edges,
)


def get_cop_glo30_spacing(bounds):

    _, min_latitude, _, max_latitude = bounds
    mean_latitude = abs((min_latitude + max_latitude) / 2)

    minimum_pixel_spacing = 0.0002777777777777778

    # Latitude spacing
    latitude_spacing = minimum_pixel_spacing

    # Longitude spacing
    if mean_latitude < 50:
        longitude_spacing = minimum_pixel_spacing
    elif mean_latitude < 60:
        longitude_spacing = minimum_pixel_spacing * 1.5
    elif mean_latitude < 70:
        longitude_spacing = minimum_pixel_spacing * 2
    elif mean_latitude < 80:
        longitude_spacing = minimum_pixel_spacing * 3
    elif mean_latitude < 85:
        longitude_spacing = minimum_pixel_spacing * 5
    elif mean_latitude < 90:
        longitude_spacing = minimum_pixel_spacing * 10
    else:
        raise ValueError("cannot resolve cop30m lattitude")

    return longitude_spacing, latitude_spacing


def get_cop_glo30_tile_transform(origin_lon, origin_lat, spacing_lon, spacing_lat):

    # Find whole degree value containing the origin
    whole_degree_origin_lon = math.floor(origin_lon)
    whole_degree_origin_lat = math.ceil(origin_lat)

    # Create the scaling from spacing
    scaling = (spacing_lon, -spacing_lat)

    # Adjust to the required offset
    adjusted_origin = adjust_pixel_coordinate_from_point_to_area(
        (whole_degree_origin_lon, whole_degree_origin_lat), scaling
    )

    transfrom = Affine.translation(*adjusted_origin) * Affine.scale(*scaling)

    return transfrom


def get_extent_of_cop_glo30_tiles_covering_bounds(bounds):

    min_lon, min_lat, max_lon, max_lat = bounds
    lon_spacing, lat_spacing = get_cop_glo30_spacing(bounds)

    # Calculate the transform, which adjusts the origin to be in area-convention coordinates
    cop_glo30_tile_transform = get_cop_glo30_tile_transform(
        min_lon, max_lat, lon_spacing, lat_spacing
    )

    # Extract the adjusted origin and scaling from the transform
    adjusted_origin_lon = cop_glo30_tile_transform.xoff
    adjusted_origin_lat = cop_glo30_tile_transform.yoff
    scaling = (cop_glo30_tile_transform.a, cop_glo30_tile_transform.e)

    # Extend the far edge to rounded degree, then adjust to area-convention coordinates
    extended_edge_lon = math.ceil(max_lon)
    extended_edge_lat = math.floor(min_lat)
    adjusted_edge_lon, adjusted_edge_lat = adjust_pixel_coordinate_from_point_to_area(
        (extended_edge_lon, extended_edge_lat), scaling
    )

    # Construct bounding box for the cop_glo30 tiles that cover the requested bounds
    adjusted_bounds = (
        adjusted_origin_lon,
        adjusted_edge_lat,
        adjusted_edge_lon,
        adjusted_origin_lat,
    )

    return adjusted_bounds, cop_glo30_tile_transform


def make_empty_cop_glo30_profile_for_bounds(bounds: tuple) -> dict:
    """make an empty cop30m dem rasterio profile based on a set of bounds.
    The desired pixel spacing changes based on lattitude
    see : https://copernicus-dem-30m.s3.amazonaws.com/readme.html

    Parameters
    ----------
    bounds : tuple
        the set of bounds (min_lon, min_lat, max_lon, max_lat)

    Returns
    -------
    dict
        A rasterio profile

    Raises
    ------
    ValueError
        If the latitude of the supplied bounds cannot be
        associated with a target pixel size
    """

    min_lon, min_lat, max_lon, max_lat = bounds
    spacing_lon, spacing_lat = get_cop_glo30_spacing(bounds)

    glo30_transform = get_cop_glo30_tile_transform(
        min_lon, max_lat, spacing_lon, spacing_lat
    )

    # Expand the bounds to the edges of pixels
    expanded_bounds, expanded_transform = expand_bounding_box_to_pixel_edges(
        bounds, glo30_transform
    )

    # Convert bounds from world to pixel to get width and height
    left_px, top_px = ~expanded_transform * (expanded_bounds[0], expanded_bounds[3])
    right_px, bottom_px = ~expanded_transform * (expanded_bounds[2], expanded_bounds[1])

    width = abs(round(right_px) - round(left_px))
    height = abs(round(bottom_px) - round(top_px))

    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "nodata": np.nan,
        "width": width,
        "height": height,
        "count": 1,
        "crs": CRS.from_epsg(4326),
        "transform": expanded_transform,
        "blockysize": 1,
        "tiled": False,
        "interleave": "band",
    }

    return expanded_bounds, profile
