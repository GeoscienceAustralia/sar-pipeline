import os
import s1_orbits
from pathlib import Path
import logging
import eof.download
from typing import Literal, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from sar_pipeline.utils.general import log_timing


@log_timing
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


@log_timing
def download_orbits(
    sentinel_file: Path,
    save_dir: Path,
    source: Literal["CDSE", "ASF"] = "CDSE",
    cdse_user: Optional[str] = None,
    cdse_password: Optional[str] = None,
    asf_user: Optional[str] = None,
    asf_password: Optional[str] = None,
) -> list[Path]:
    """
    Downloads precise/restituted orbit files (.EOF files) for the given Sentinel-1 SAFE file from the
    Copernicus Data Space Ecosystem (CDSE) or Alaska Satellite Facility (ASF) datahubs.

    Parameters
    ----------
    sentinel_file : Path
        Path to the Sentinel-1 SAFE file.
    save_dir : Path
        Directory to save the downloaded EOF file.
    source : Literal["CDSE", "ASF"], optional
        Source for downloading EOF, either "CDSE" or "ASF". Defaults to "CDSE".
    cdse_user : Optional[str], optional
        CDSE username. Defaults to None.
    cdse_password : Optional[str], optional
        CDSE password. Defaults to None.
    asf_user : Optional[str], optional
        ASF username. Defaults to None.
    asf_password : Optional[str], optional
        ASF password. Defaults to None.

    Returns
    -------
    list[Path]
        List of paths for downloaded orbit files

    Raises
    ------
    ValueError
        If required credentials are missing.
    """

    if source == "CDSE":
        cdse_user = cdse_user or os.getenv("CDSE_LOGIN")
        cdse_password = cdse_password or os.getenv("CDSE_PASSWORD")
        if not cdse_user or not cdse_password:
            raise ValueError(
                "CDSE credentials are not set. Provide them as arguments or set CDSE_LOGIN and CDSE_PASSWORD as environment variables."
            )
        asf_user, asf_password = None, None

    elif source == "ASF":
        asf_user = asf_user or os.getenv("EARTHDATA_LOGIN")
        asf_password = asf_password or os.getenv("EARTHDATA_PASSWORD")
        if not asf_user or not asf_password:
            raise ValueError(
                "ASF credentials are not set. Provide them as arguments or set EARTHDATA_LOGIN and EARTHDATA_PASSWORD as environment variables."
            )
        cdse_user, cdse_password = None, None

    else:
        raise ValueError(f"Source must be either 'CDSE' or 'ASF', got '{source}'.")

    logger.info(f"Starting EOF download from {source}...")

    # The logic in eof.download.main() tries CDSE first by default. set force_asf by source
    orbit_paths = eof.download.main(
        sentinel_file=sentinel_file,
        save_dir=save_dir,
        cdse_user=cdse_user,
        cdse_password=cdse_password,
        force_asf=source == "ASF",
        asf_user=asf_user,
        asf_password=asf_password,
    )

    if len(orbit_paths) > 1:
        raise ValueError(
            f"{len(ORBIT_PATHS)} orbit paths found for scene. Expecting 1."
        )
    return orbit_paths
