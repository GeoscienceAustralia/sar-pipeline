from dem_handler.utils.spatial import check_dem_type_in_bounds
from typing import Literal

VALID_DEMS = ["best", "cop_glo30", "REMA_32", "REMA_10", "REMA_2"]
VALID_REMA_RESOLUTIONS = [2, 10, 32]
ValidDemType = Literal[*VALID_DEMS]
ValidREMAResolution = Literal[*VALID_REMA_RESOLUTIONS]


def get_best_dem_type_for_scene(
    bounds: tuple | list, rema_resolution: ValidREMAResolution = 32
) -> ValidDemType:
    """Get the best dem_type for processing based on the location bounds.
    Returns either the REMA dem or the Copernicus Global 30m DEM (cop_glo30).

    The logic prioritises the REMA DEM for high latitude areas (<-50 degrees).
    However, if in a high latitude areas there is no intersection with the
    REMA dem, but there is intersection with the cop_glo30 DEN, the cop_glo30
    DEM will be returned. An example of this is Heard Island which has a high
    latitude but is not in the REMA area of interest.


    Parameters
    ----------
    bounds : tuple | list
        bounds of scene in degrees (left, bottom, right, top)
    rema_resolution : int, ValidREMAResolution
        resolution of the REMA DEM, by default 32

    Returns
    -------
    ValidDemType
        The best DEM type for the area
    """

    minimum_lat = min(bounds[1], bounds[3])

    # pick the correct Literal value explicitly
    if rema_resolution == 32:
        REMA = "REMA_32"
    elif rema_resolution == 10:
        REMA = "REMA_10"
    elif rema_resolution == 2:
        REMA = "REMA_2"
    else:
        raise ValueError(f"Unsupported REMA resolution: {rema_resolution}")

    if minimum_lat > -50:
        return "cop_glo30"
    else:
        if check_dem_type_in_bounds("REMA", rema_resolution, bounds):
            return REMA
        elif check_dem_type_in_bounds("cop_glo30", 30, bounds):
            return "cop_glo30"
        else:
            return REMA
