from pathlib import Path

from sar_pipeline.utils.sentinel1 import (
    get_product_type_from_scene_id,
    get_dates_from_scene_id,
)

SCENE_DIR = Path("/g/data/fj7/Copernicus/Sentinel-1/C-SAR/")


def find_scene_file_from_id(scene_id: str) -> Path:
    """Finds the path to the scene on GADI based on the scene ID

    Parameters
    ----------
    scene_id : str
        Sentinel-1 scene ID
        e.g. S1A_EW_GRDM_1SDH_20220612T120348_20220612T120452_043629_053582_0F6

    Returns
    -------
    Path
        Location of scene on NCI GADI

    Raises
    ------
    RuntimeError
        Found more than one file -- expects one
    RuntimeError
        Found no files -- expects one. Or another Error
    """

    scene_product = get_product_type_from_scene_id(scene_id)

    # Parse the scene dates -- only start date is needed for search
    scene_start, _ = get_dates_from_scene_id(scene_id)

    # Extract year and month of first path to provide for file search
    year = scene_start.strftime("%Y")
    month = scene_start.strftime("%m")

    # Set path on GADI and search
    search_path = SCENE_DIR.joinpath(f"{scene_product}/{year}/{year}-{month}/")
    file_path = list(search_path.rglob(f"{scene_id}.zip"))

    # Identify file
    if len(file_path) == 1:
        scene_path = file_path[0]
    elif len(file_path) > 1:
        raise RuntimeError("More than one file found. Review before proceeding")
    else:
        raise RuntimeError(
            "No files found or some other error. Review before proceeding"
        )

    return scene_path
