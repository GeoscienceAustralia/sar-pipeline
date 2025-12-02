import os
import s1_orbits
from pathlib import Path
import logging
import eof.download
from typing import Literal, Optional, Union
from datetime import datetime, timedelta
import subprocess
import re

from sar_pipeline.utils.general import log_timing
from sar_pipeline.utils.sentinel1 import get_dates_from_scene_id
from sar_pipeline.preparation.downloads.scenes import (
    create_asf_netrc_file,
    MissingCredentialsError,
    _run_aus_cophub_query,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_ORBIT_DATA_SOURCES = ["AUS_COP_HUB", "ASF", "CDSE"]
ValidOrbitDataSources = Literal["AUS_COP_HUB", "ASF", "CDSE"]


class OrbitDownloadError(Exception):
    """Exception raised when the scene download fails."""

    pass


class OrbitNotFoundError(Exception):
    """Exception raised when orbit file cannot be found."""

    pass


class NonSingleOrbitError(Exception):
    """Exception raised when more than one orbit file is found."""

    pass


@log_timing
def download_orbits_from_s3(
    scene: str, download_folder: Path, make_folder=True
) -> Path:
    """For the given scene, downloads the AUX_POEORB file if available,
    otherwise downloads the AUX_RESORB file.

    Parameters
    ----------
    scene : str
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
    logger.info(f"Orbit file downloaded : {orbit_file}")
    return orbit_file


def download_orbits_from_asf(
    scene_safe_file: Path,
    download_folder: Path,
    asf_user: Optional[str] = None,
    asf_password: Optional[str] = None,
) -> list:
    """For the given scene, downloads the AUX_POEORB file if available,
    otherwise downloads the AUX_RESORB file from the ASF. Falls back
    to creating and using a .netrc file with the credentials if it fails
    setting them at runtime.

    Parameters
    ----------
    scene_safe_file : Path
        Path to the SAFE file for the scene
    download_folder : Path
        Folder where the orbit file will be saved.
    asf_user : Optional[str], optional
        User for NASA Earthdata, by default None and environment credentials
        will be searched for EARTHDATA_LOGIN.
    asf_password : Optional[str], optional
        Password for NASA Earthdata, by default None and environment credentials
        will be searched for EARTHDATA_PASSWORD.

    Returns
    -------
    list
        List of paths to downloaded orbit files

    Raises
    ------
    MissingCredentialsError
        Required Credentials are missing.
    """

    asf_user = asf_user or os.getenv("EARTHDATA_LOGIN")
    asf_password = asf_password or os.getenv("EARTHDATA_PASSWORD")
    if not asf_user or not asf_password:
        logging.error(
            "ASF credentials are not set. Provide them as arguments or set EARTHDATA_LOGIN and EARTHDATA_PASSWORD as environment variables."
        )
        raise MissingCredentialsError()
    if not os.getenv("NETRC"):
        # create the netrc if not existing for authentication
        create_asf_netrc_file(asf_user, asf_password)

    try:
        orbit_paths = eof.download.main(
            sentinel_file=scene_safe_file,
            save_dir=download_folder,
            cdse_user=None,
            cdse_password=None,
            force_asf=True,
            asf_user=asf_user,
            asf_password=asf_password,
        )
    except:
        # authentication through session credentials may have failed (ASF bug)
        # remove explicit credentials to read tem from from .netrc
        logger.info("ASF credentials failed. Falling back to .netrc authentication")
        orbit_paths = eof.download.main(
            sentinel_file=scene_safe_file,
            save_dir=download_folder,
            cdse_user=None,
            cdse_password=None,
            force_asf=True,
        )
    return orbit_paths


def download_orbits_from_cdse(
    scene_safe_file: Path,
    download_folder: Path,
    cdse_user: Optional[str] = None,
    cdse_password: Optional[str] = None,
) -> list:
    """For the given scene, downloads the AUX_POEORB file if available,
    otherwise downloads the AUX_RESORB file from the CDSE.

    Parameters
    ----------
    scene_safe_file : Path
        Path to the SAFE file for the scene
    download_folder : Path
        Folder where the orbit file will be saved.
    asf_user : Optional[str], optional
        User for CDSE, by default None and environment credentials
        will be searched for CDSE_LOGIN.
    asf_password : Optional[str], optional
        Password for CDSE, by default None and environment credentials
        will be searched for CDSE_PASSWORD.

    Returns
    -------
    list
        List of paths to downloaded orbit files

    Raises
    ------
    MissingCredentialsError
        Required Credentials are missing.
    """

    cdse_user = cdse_user or os.getenv("CDSE_LOGIN")
    cdse_password = cdse_password or os.getenv("CDSE_PASSWORD")
    if not cdse_user or not cdse_password:
        logger.error(
            "CDSE credentials are not set. Provide them as arguments or set CDSE_LOGIN and CDSE_PASSWORD as environment variables."
        )
        raise MissingCredentialsError

    orbit_paths = eof.download.main(
        sentinel_file=scene_safe_file,
        save_dir=download_folder,
        cdse_user=cdse_user,
        cdse_password=cdse_password,
        force_asf=False,
    )
    return orbit_paths


@log_timing
def download_orbits_from_aus_cop_hub(
    scene_safe_file: str | Path,
    download_folder: Path,
    make_folder: bool = True,
    search_buffer_days=2,
    orbit_file_types: list = ["AUX_POEORB", "AUX_RESORB"],
    aus_cop_hub_login: Optional[str] = None,
    aus_cop_hub_pass: Optional[str] = None,
    aus_cop_hub_client_id: Optional[str] = None,
    aus_cop_hub_client_secret: Optional[str] = None,
    service: str = "https://catalogue.copernicus.gov.au/odata/v1",
    token_url: str = "https://auth.copernicus.gov.au/realms/gss/protocol/openid-connect/token",
    pygssearch_conda_env: Optional[Union[str, Path]] = None,
):
    """Download the orbits from the Copernicus Australasia Regional Data Hub. Function makes use of
    pygssearch - https://pypi.org/project/pygssearch/ which is installed in a separate conda environment
    and called in a subprocess due to package conflicts. The path to the conda environment
    can be set in the function or as an environment variable (e.g. defined in the isce3_rtc/Dockerfile).

    Parameters
    ----------
    scene_safe_file : str | Path
        Path to the scene .SAFE file e.g. path/to/S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD.SAFE
    download_folder : Path
        Folder where the scene should be downloaded to
    make_folder : bool, optional
        Make non-existing folders, by default True
    orbit_file_types:
        Preference for the type of orbit file to be downloaded. Default ["AUX_POEORB", "AUX_RESORB"].
    aus_cop_hub_login : str | None, optional
        Login name for the Hub, by default None. If not specified env variable
        AUS_COP_HUB_LOGIN will be used.
    aus_cop_hub_pass : str | None, optional
        Login password credential for the Hub, by default None. If not specified env variable
        AUS_COP_HUB_PASSWORD will be used.
    aus_cop_hub_client_id : str | None, optional
        Client id to be used for the Hub. e.g. odata. By default None. If not specified env variable
        AUS_COP_HUB_CLIENT_ID will be used.
    aus_cop_hub_client_secret : str | None, optional
        Client secret credential for the Hub, by default None. If not specified env variable
        AUS_COP_HUB_CLIENT_SECRET will be used. Value was provided by hub developers at GA.
    service : str, optional
        Service to query, by default "https://catalogue.copernicus.gov.au/odata/v1"
    token_url : str, optional
        URL to validate token, by default "https://auth.copernicus.gov.au/realms/gss/protocol/openid-connect/token"
    pygssearch_conda_env: Optional[Union[str, Path]]
        Path to the conda environment containing an installation of pygssearch that will be called in a
        subprocess. If not specified, If not specified env variable PYGSSEARCH_CONDA_ENV will be used.
        e.g. /path/to/anaconda3/envs/pygssearch-env

    Returns
    -------
    list
        List of paths to the downloaded orbit files.

    Raises
    ------
    MissingCredentialsError
    """

    # get the scene name from the SAFE path
    scene = Path(scene_safe_file).stem

    # Fallback to environment variables if arguments are not provided
    aus_cop_hub_login = aus_cop_hub_login or os.getenv("AUS_COP_HUB_LOGIN")
    aus_cop_hub_pass = aus_cop_hub_pass or os.getenv("AUS_COP_HUB_PASSWORD")
    aus_cop_hub_client_id = aus_cop_hub_client_id or os.getenv("AUS_COP_HUB_CLIENT_ID")
    aus_cop_hub_client_secret = aus_cop_hub_client_secret or os.getenv(
        "AUS_COP_HUB_CLIENT_SECRET"
    )
    pygssearch_conda_env = pygssearch_conda_env or os.getenv("PYGSSEARCH_CONDA_ENV")

    # Check for any missing credentials
    missing_vars = []
    if not aus_cop_hub_login:
        missing_vars.append("AUS_COP_HUB_LOGIN")
    if not aus_cop_hub_pass:
        missing_vars.append("AUS_COP_HUB_PASSWORD")
    if not aus_cop_hub_client_id:
        missing_vars.append("AUS_COP_HUB_CLIENT_ID")
    if not aus_cop_hub_client_secret:
        missing_vars.append("AUS_COP_HUB_CLIENT_SECRET")

    if missing_vars:
        raise MissingCredentialsError(
            f"Missing credentials: {', '.join(missing_vars)}. Please pass them as arguments or set them as environment variables."
        )

    # Create a folder for download if requested
    if make_folder:
        os.makedirs(download_folder, exist_ok=True)

    # Run the initial query to get the base run command plus scene metadata.
    pygssearch_conda_env = pygssearch_conda_env or os.getenv("PYGSSEARCH_CONDA_ENV")

    # Set the command to use conda to execute a command using the pygssearch environment
    environment_cmd = f"conda run -p {pygssearch_conda_env} "

    # get the start and end dates for a scene
    scene_st_datetime, scene_end_datetime = get_dates_from_scene_id(scene)
    search_st = (scene_st_datetime - timedelta(days=search_buffer_days)).strftime(
        "%Y-%m-%d"
    )
    search_et = (scene_end_datetime + timedelta(days=search_buffer_days)).strftime(
        "%Y-%m-%d"
    )
    orbit_file_name = None
    for orbit_file_type in orbit_file_types:
        logger.info(
            f"Querying AUS_COP_HUB for orbit type {orbit_file_type} between {search_st} and {search_et}"
        )
        search_query = f"pygssearch --service {service} --mission 1 --product_type {orbit_file_type} --start {search_st} --end {search_et} --format _"
        # Set the query for the scene -- no credentials required when querying
        pygss_search_cmd = environment_cmd + search_query
        # run the auscophub query
        aus_cophub_orbit_metadata = _run_aus_cophub_query(
            pygssearch_conda_env, pygss_search_cmd
        )
        logger.info(f"{len(aus_cophub_orbit_metadata)} results found.")
        if len(aus_cophub_orbit_metadata) == 0:
            logger.info(
                f"Could not find orbit type {orbit_file_type} in provided time window"
            )
            if orbit_file_type == orbit_file_types[-1]:
                return []
        logger.info(f"Filtering for best orbit file")
        for orb in aus_cophub_orbit_metadata:
            orb_st = datetime.strptime(
                orb["ContentDate"]["Start"], "%Y-%m-%dT%H:%M:%S.%fZ"
            )
            orb_et = datetime.strptime(
                orb["ContentDate"]["End"], "%Y-%m-%dT%H:%M:%S.%fZ"
            )
            if (scene_st_datetime > orb_st) and (scene_end_datetime < orb_et):
                orbit_file_name = orb["Name"]
                logger.info(f"match': {orbit_file_name}")
                break
        if orbit_file_name:
            break
        if not orbit_file_name and orbit_file_type == orbit_file_types[-1]:
            # exit with no file path found
            return []

    # Add additional query parameters to the base command to enable downloading
    download_query = (
        f"pygssearch --service {service} "
        f"--username {aus_cop_hub_login} "
        f"--password {aus_cop_hub_pass} "
        f"--token_url {token_url} "
        f"--client_id {aus_cop_hub_client_id} "
        f"--client_secret {aus_cop_hub_client_secret} "
        f"--name {orbit_file_name}"
        f"--download "
        f"--output {download_folder} "
    )

    try:
        logger.info(f"Download in progress...")
        process = subprocess.Popen(
            environment_cmd + download_query,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Given command is run in a conda environment,
        # progress logs may not be returned until completion
        for line in process.stdout:
            line = line.strip()
            # remove sensitive info from logs
            sanitised_line = re.sub(
                r"(--?(client_secret|password)[=\s]+)\S+", r"\1****", line
            )
            logger.info(sanitised_line)

        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"Download failed with return code {return_code}")

    except Exception as e:
        logger.error("An error occurred while running the download command")
        raise

    # form the orbit path
    return [Path(download_folder) / orbit_file_name]


@log_timing
def download_orbits_from_preference_list(
    scene_safe_file: Path,
    download_folder: Path,
    orbit_data_source_preferences: (
        ValidOrbitDataSources | list[ValidOrbitDataSources]
    ) = VALID_ORBIT_DATA_SOURCES,
) -> list[Path]:
    """
    Downloads precise/restituted orbit files (.EOF files) for the given
    Sentinel-1 SAFE file from the Copernicus Australia Datahub (AUS_COP_HUB),
    Copernicus Data Space Ecosystem (CDSE) or Alaska Satellite Facility (ASF).

    Parameters
    ----------
    scene_safe_file : Path
        Path to the Sentinel-1 SAFE file.
    download_folder : Path
        Directory to save the downloaded EOF file.
    orbit_data_source_preferences : ValidOrbitDataSources | list[ValidOrbitDataSources], optional
        Source for downloading EOF, either "AUS_COP_HUB, "CDSE" or "ASF",
        or a list of preferences. Defaults to ["AUS_COP_HUB", "ASF", "CDSE"].

    Returns
    -------
    string[Path]
        Path to the downloaded orbit file

    Raises
    ------
    ValueError
        Not a valid orbit source.
    OrbitNotFoundError
        Orbit file not found.
    NonSingleOrbitError
        Multiple orbit files found for scene.
    MissingCredentialsError
        Credentials not set for required source.
    """

    # if single string provided, add to list of preferences to iterate
    if isinstance(orbit_data_source_preferences, str):
        orbit_data_source_preferences = [orbit_data_source_preferences]

    for i, source in enumerate(orbit_data_source_preferences):
        logger.info(
            f"Attempting to download orbits from preference {i+1} of {len(orbit_data_source_preferences)} : {source}"
        )
        try:
            if source == "CDSE":
                orbit_paths = download_orbits_from_cdse(
                    scene_safe_file=scene_safe_file,
                    download_folder=download_folder,
                )

            elif source == "ASF":
                orbit_paths = download_orbits_from_asf(
                    scene_safe_file=scene_safe_file,
                    download_folder=download_folder,
                )

            elif source == "AUS_COP_HUB":
                orbit_paths = download_orbits_from_aus_cop_hub(
                    scene_safe_file=scene_safe_file,
                    download_folder=download_folder,
                )

            else:
                raise ValueError(
                    f"Source must be either one of {VALID_ORBIT_DATA_SOURCES}, got '{source}'."
                )

            if len(orbit_paths) == 1:
                logging.info(
                    f"Orbit file successfully downloaded from {source} : {orbit_paths[0]}"
                )
                break
            if len(orbit_paths) == 0:
                raise OrbitNotFoundError(f"Orbit file could not be found for scene.")
            elif len() > 1:
                raise NonSingleOrbitError(
                    f"Check logic, {len(orbit_paths)} orbit files found for scene. Expecting 1."
                )
        except Exception as e:
            logger.error(
                f"Could not download orbits from preference {i+1} of {len(orbit_data_source_preferences)} : {source}",
                exc_info=True,
            )
            if source == orbit_data_source_preferences[-1]:
                raise OrbitDownloadError(
                    f"Orbits could not be downloaded from any data source provided : {orbit_data_source_preferences}"
                )

    return orbit_paths[0]
