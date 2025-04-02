import os
import s1_orbits
from pathlib import Path
import logging
import eof.download

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

def download_eof(
    sentinel_file: str,
    save_dir: Path | str,
    cdse_user: str | None = None,
    cdse_password: str | None = None,
    force_asf: bool = False,
):
    """
    Downloads an EOF file for the given Sentinel-1 SAFE file.

    Args:
        sentinel_file (str): Path to the Sentinel-1 SAFE file.
        save_dir (Path | str): Directory to save the downloaded EOF file.
        cdse_user (str | None, optional): CDSE username. Defaults to None.
        cdse_password (str | None, optional): CDSE password. Defaults to None.
        force_asf (bool, optional): Whether to force download from ASF. Defaults to False.

    Returns:
        str: Path to the downloaded EOF file.

    Raises:
        ValueError: If CDSE credentials are not set through arguments or environment variables.
    """
    # Check credentials
    cdse_user = cdse_user or os.getenv("CDSE_LOGIN")
    cdse_password = cdse_password or os.getenv("CDSE_PASSWORD")
    
    if not cdse_user or not cdse_password:
        raise ValueError("CDSE credentials are not set. Provide them as arguments or set CDSE_LOGIN and CDSE_PASSWORD as environment variables.")
    
    logging.info("Starting EOF download...")
    return eof.download.main(
        sentinel_file=sentinel_file,
        cdse_user=cdse_user,
        cdse_password=cdse_password,
        force_asf=force_asf,
        save_dir=save_dir
    )
