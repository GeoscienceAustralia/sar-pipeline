import os
import s1_orbits
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_orbits_from_s3(
    scene: str, download_folder: Path, make_folder=True
) -> Path:
    """_summary_

    Parameters
    ----------
    scene : str
        For the given scene, downloads the AUX_POEORB file if available, otherwise downloads the AUX_RESORB file
        S1A_IW_SLC__1SDV_20230727T075102_20230727T075131_049606_05F70A_AE0A
    download_folder : Path
        Path to where the orbit shold be downloaded
    make_folder : bool, optional
        Whether to make the download folder, by default True

    Returns
    -------
    _type_
        _description_
    """
    # https://s1-orbits.s3.us-west-2.amazonaws.com/README.html
    if make_folder:
        os.makedirs(download_folder, exist_ok=True)
    logger.info(f"Downloading orbits for : {scene}")
    orbit_file = s1_orbits.fetch_for_scene(scene, dir=download_folder)
    # TODO handle no orbit found
    logger.info(f"Orbit file downloaded : {orbit_file}")
    return orbit_file
