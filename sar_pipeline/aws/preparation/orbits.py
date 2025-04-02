import os
import s1_orbits
from pathlib import Path
import logging
import eof.download
from typing import Literal

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

def download_orbits_from_datahub(
    sentinel_file: Path,
    save_dir: Path,
    source: Literal["CDSE", "ASF"] = "CDSE",
    cdse_user: str | None = None,
    cdse_password: str | None = None,
    force_asf: bool = False,
) -> Path:
    """
    Downloads precise/restituted orbit files (.EOF files) for the given Sentinel-1 SAFE file from the
    Copernicus Data Space Ecosystem (CDSE) or Alaskan Space Facility (ASF) datahubs. 

    Args:
        sentinel_file (Path): Path to the Sentinel-1 SAFE file.
        save_dir (Path): Directory to save the downloaded EOF file.
        source (Literal["CDSE", "ASF"], optional): Source for downloading EOF, either "CDSE" or "ASF". Defaults to "CDSE".
        cdse_user (str | None, optional): CDSE username. Defaults to None.
        cdse_password (str | None, optional): CDSE password. Defaults to None.
        force_asf (bool, optional): If True, forces download from ASF, bypassing CDSE. Defaults to False.

    Returns:
        Path: Path to the downloaded EOF file.
    
    Raises:
        ValueError: If source is not recognised or credentials are not set through arguments or environment variables.
    """
    # The logic in eof.download.main() tries CDSE first by default.
    # Passing this to the force_asf argument skips checking CDSE first and goes directly to ASF.
    use_asf = source == "ASF"

    if source == "CDSE":
        cdse_user = cdse_user or os.getenv("CDSE_LOGIN")
        cdse_password = cdse_password or os.getenv("CDSE_PASSWORD")
        if not cdse_user or not cdse_password:
            raise ValueError("CDSE credentials are not set. Provide them as arguments or set CDSE_LOGIN and CDSE_PASSWORD as environment variables.")
        asf_user, asf_password = None, None
    elif source == "ASF":
        asf_user = asf_user or os.getenv("EARTHDATA_LOGIN")
        asf_password = asf_password or os.getenv("EARTHDATA_PASSWORD")
        if not asf_user or not asf_password:
            raise ValueError("ASF credentials are not set. Provide them as arguments or set EARTHDATA_LOGIN and EARTHDATA_PASSWORD as environment variables.")
        cdse_user, cdse_password = None, None
    else:
        raise ValueError(f"Source can be either CDSE or ASF, but {source} was used.")
    
    logging.info(f"Starting EOF download from {source}...")
    return eof.download.main(
        sentinel_file=sentinel_file,
        save_dir=save_dir
        cdse_user=cdse_user,
        cdse_password=cdse_password,
        force_asf=use_asf,
        asf_user=asf_user,
        asf_password=asf_password,
    )
