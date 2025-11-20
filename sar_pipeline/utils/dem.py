from dem_handler.utils.spatial import check_dem_type_in_bounds

VALID_DEMS = ["best", "cop_glo30", "REMA_32", "REMA_10", "REMA_2"]


def get_best_dem_type_for_scene(bounds):
    """Get the best dem_type for processing based on the set of bounds.
    The following logic is implemented that prioritises the REMA DEM
    for high latitude areas.

    if the minimum latitude is above -50 degrees:
        return 'cop30_dem'
    if the minimum latitude is below -50 degrees:
        if the bounds intersects the REMA DEM:
            return 'REMA_32'
        elif the bounds intersect the copernicus 30m DEM:
            # an example of this is Heard Island which is below
            # 50 degrees south but not covered by the REMA product
            return 'cop_glo30'
        else:
            return 'REMA_32'

    Parameters
    ----------
    bounds : list | tuple
        (left, bottom, right, top) in degrees
    """

    minimum_lat = min(bounds[1], bounds[3])
    if minimum_lat > -50:
        return "cop_glo30"
    else:
        if check_dem_type_in_bounds("REMA", 32, bounds):
            return "REMA_32"
        elif check_dem_type_in_bounds("cop_glo30", 30, bounds):
            return "cop_glo30"
        else:
            return "REMA_32"
