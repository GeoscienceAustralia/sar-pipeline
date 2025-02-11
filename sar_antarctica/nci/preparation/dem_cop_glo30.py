from affine import Affine
import math
from sar_antarctica.utils.raster import adjust_pixel_coordinate_from_point_to_area
from sar_antarctica.nci.preparation.dem import find_required_dem_paths_from_index
from shapely.geometry import box


def get_cop_glo30_spacing(bounds):

    _, min_latitude, _, max_latitude = bounds
    mean_latitude = abs((min_latitude + max_latitude) / 2)

    minimum_pixel_spacing = 0.0002777777777777778

    # Defined as negative to allow for use of top-down coordinates when working with pixel space
    latitude_spacing = -minimum_pixel_spacing

    # Defined as positive to allow for use of left-right coordinates when working with pixel space
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


def identify_extent_of_cop_glo30_tiles_covering_bounds(bounds):

    spacing = get_cop_glo30_spacing(bounds)

    min_x, min_y, max_x, max_y = bounds

    left_most_decimal_degree = math.floor(min_x)
    right_most_decimal_dregee = math.ceil(max_x)
    bottom_most_decimal_degree = math.floor(min_y)
    top_most_decimal_degree = math.ceil(max_y)

    # Adjust the decimal degrees by half the spacing in each direction to account for
    # Cop GLO30 using point-based coordinates. This converts the extents to area-based

    adjusted_top_left = adjust_pixel_coordinate_from_point_to_area(
        (left_most_decimal_degree, top_most_decimal_degree), spacing
    )
    adjusted_bottom_right = adjust_pixel_coordinate_from_point_to_area(
        (right_most_decimal_dregee, bottom_most_decimal_degree), spacing
    )

    extent_min_x, extent_max_y = adjusted_top_left
    extent_max_x, extent_min_y = adjusted_bottom_right

    extent_bounds = (extent_min_x, extent_min_y, extent_max_x, extent_max_y)
    extent_affine = Affine.translation(*adjusted_top_left) * Affine.scale(*spacing)

    return extent_bounds, extent_affine


# def create_cop_glo30_vrt_from_bounds(bounds, tile_index):

#     # Update the bounding box if desired (e.g. with additional buffer to account for warping)

#     # Calculate the expected dem bounds to write to using
#     # dem_vrt_extent = identify_extent_of_cop_glo30_tiles_covering_bounds

#     # Get the DEM tiles that intersect with the bounding box

#     # If no dem tiles are found
#         # write a raster with the appropriate profile containing all zeros

#     # If dem tiles are found
#         # Build VRT using dem_vrt_extent with merge_raster files
#         # Read the data out of the VRT using read_vrt_in_bounds (noting that this can be updated to use expand_bounding_box_to_pixel_edges)
