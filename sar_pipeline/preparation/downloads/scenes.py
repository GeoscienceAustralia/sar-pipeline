import asf_search
from asf_search import ASFSearchResults
import os
from pathlib import Path
import logging
import zipfile
import subprocess
import shapely
import ast
import re
import tempfile
from cdsetool.query import query_features, FeatureQuery
from cdsetool.credentials import Credentials
from cdsetool.download import download_features
from cdsetool.monitor import StatusMonitor

from sar_pipeline.utils.general import log_timing
from sar_pipeline.utils.sentinel1 import extract_metadata_from_s1_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_SCENE_DATA_SOURCES = ["AUS_COP_HUB", "CDSE", "ASF"]


class MissingCredentialsError(Exception):
    """Exception raised when no credentials are supplied."""

    pass


class SceneDownloadError(Exception):
    """Exception raised when the scene download fails."""

    pass


class NonSingleSceneResultError(Exception):
    """Exception raised 0, or more than one SLC result is found."""

    pass


def query_scene_from_asf(scene: str) -> ASFSearchResults:
    """Query a scene from ASF. GRD, SLC, OCN, or RAW.

    Parameters
    ----------
    scene : str
        Scene of interest. E.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD

    Returns
    -------
    ASFSearchResults
        Search results from ASF.

    Raises
    ------
    ValueError
        Non supported product type
    """

    logger.info(f"Searching ASF for scene")

    # Extract metadata from scene ID
    scene_metadata = extract_metadata_from_s1_id(scene)

    # Determine the asf_search product type to search: https://github.com/asfadmin/Discovery-asf_search/blob/master/asf_search/constants/PRODUCT_TYPE.py
    # GRD processingly level query cannot currently be determined from product type alone, so list all GRD and assume it is one of these five.
    # The list is sufficient to distinguish metadata files from data files
    if scene_metadata.product_type == "GRD":
        processing_level_query = ["GRD_HD", "GRD_MD", "GRD_MS", "GRD_HS", "GRD_FD"]
    elif scene_metadata.product_type in ["SLC", "OCN", "RAW"]:
        processing_level_query = scene_metadata.product_type
    else:
        raise ValueError(
            f"Product type {scene_metadata.product_type} not recognised. Should be one of GRD, SLC, OCN, or RAW"
        )

    # Run the search
    search_results = asf_search.granule_search(
        [scene], asf_search.ASFSearchOptions(processingLevel=processing_level_query)
    )

    return search_results


def create_asf_netrc_file(asf_login: str, asf_pass: str) -> Path:
    """
    Create a temporary `.netrc` file containing ASF/Earthdata login credentials.

    This function generates a temporary `.netrc` file to authenticate with the
    Alaska Satellite Facility (ASF) or NASA Earthdata services. The file is
    written to a secure temporary location, assigned appropriate file permissions
    (`chmod 600`), and its path is set as the `NETRC` environment variable so that
    tools using `requests` or other netrc-aware libraries can locate it.

    Parameters
    ----------
    asf_login : str
        The username associated with the ASF/NASA Earthdata account.
    asf_pass : str
        The password associated with the ASF/NASA Earthdata account.

    Returns
    -------
    Path
        The filesystem path to the created temporary `.netrc` file.
    """

    logger.info(f"Creating temporary .netrc file with ASF/Earthdata credentials")
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write(
            f"""machine urs.earthdata.nasa.gov
        login {asf_login}
        password {asf_pass}
        """
        )
        netrc_path = f.name

    logger.info(f"Temporary .netrc created at {netrc_path}")

    # Set file permissions to 600 (required)
    os.chmod(netrc_path, 0o600)

    # Optional: tell requests/netrc-aware tools to use this file
    os.environ["NETRC"] = netrc_path

    return netrc_path


@log_timing
def download_scene_from_asf(
    scene: str,
    download_folder: Path,
    make_folder: bool = True,
    unzip: bool = True,
    asf_login: str | None = None,
    asf_pass: str | None = None,
) -> tuple[str, dict]:
    """Download a scene from the ASF

    Parameters
    ----------
    scene : str
        Scene of interest. E.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD
    download_folder : Path
        Folder to download file to.
    make_folder : bool, optional
        Make non-existing folders, by default True
    unzip : bool, optional
        Unzip the downloaded file, by default True
    asf_login : str | None, optional
        Login for the ASF, by default None. If not specified env variable
        EARTHDATA_LOGIN will be used.
    asf_pass : str | None, optional
        Login for the ASF, by default None. If not specified env variable
        EARTHDATA_PASSWORD will be used.

    Returns
    -------
    tuple[str,dict]
        Path to downloaded scene and dict of metadata

    Raises
    ------
    MissingCredentialsError
        Required credentials are not set
    NonSingleSceneResultError
        0, or more than one SLC result is found.
    SceneDownloadError
        Error with download
    """

    # Search for scene on ASF
    search_results = query_scene_from_asf(scene)

    # ensure only one slc found
    if len(search_results) != 1:
        raise NonSingleSceneResultError(
            f"Expected 1 SLC, found {len(search_results)} for scene : {scene}"
        )
    else:
        asf_scene_metadata = search_results[0]

    scene_name = asf_scene_metadata.properties["sceneName"]

    # Authenticate. If credentials not supplied search the environment variables
    if asf_login is None and asf_pass is None:
        asf_login = os.getenv("EARTHDATA_LOGIN")
        asf_pass = os.getenv("EARTHDATA_PASSWORD")
        if not asf_login or asf_pass:
            err_string = (
                "Not all credentials supplied. Please provide a asf_login and asf_pass "
                "or set the EARTHDATA_LOGIN and EARTHDATA_PASSWORD environment variables"
            )
            MissingCredentialsError(err_string)

    # create the NETRC file if it doesn't exist
    # this is a fallback if auth_with_creds fails
    if not os.getenv("NETRC"):
        create_asf_netrc_file(asf_login, asf_pass)

    try:
        logger.info("Attempting to authenticate with ASF session")
        session = asf_search.ASFSession()
        session.auth_with_creds(asf_login, asf_pass)
        use_session = True
    except:
        logger.error(
            "ASF session authentication failed. Attempting fo fall back to .netrc file.",
            exc_info=True,
        )
        use_session = False

    if make_folder:
        os.makedirs(download_folder, exist_ok=True)

    logger.info(f"Downloading : {scene_name}")
    scene_zip_path = Path(download_folder) / f"{scene_name}.zip"
    scene_safe_path = scene_zip_path.with_suffix(".SAFE")

    if scene_safe_path.exists() and unzip:
        logger.info(f"Skipping download, unzipped scene exists at : {scene_safe_path}")
    elif scene_zip_path.exists():
        logger.info(f"Skipping download, zipped scene exists at : {scene_zip_path}")
    else:
        try:
            if use_session:
                asf_scene_metadata.download(path=download_folder, session=session)
            else:
                # Default to looking for the .netrc file for authentication if no session is provided.
                asf_scene_metadata.download(path=download_folder)
        except:
            logger.error(
                "An error occurred while running the download command",
                exc_info=True,
            )
            raise SceneDownloadError

    if unzip and not scene_safe_path.exists():
        logger.info(f"unzipping scene to {scene_safe_path}")
        with zipfile.ZipFile(scene_zip_path, "r") as zip_ref:
            zip_ref.extractall(download_folder)
        return scene_safe_path, asf_scene_metadata
    elif scene_safe_path.exists() and unzip:
        return scene_safe_path, asf_scene_metadata
    else:
        return scene_zip_path, asf_scene_metadata


def query_scene_from_cdse(scene: str) -> FeatureQuery:
    """Query scene metadata from the CDSE

    Parameters
    ----------
    scene : str
        Scene of interest. E.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD

    Returns
    -------
    FeatureQuery
        Scene metadata as a FeatureQuery class
    """

    logger.info(f"Searching CDSE for scene metadata")

    cdse_scenes_metadata = query_features(
        "Sentinel1",
        {
            "productIdentifier": scene,
        },
    )

    return cdse_scenes_metadata


@log_timing
def download_scene_from_cdse(
    scene: str,
    download_folder: Path,
    make_folder: bool = True,
    unzip: bool = True,
    cdse_login: str | None = None,
    cdse_pass: str | None = None,
) -> tuple[str, dict]:
    """Download a scene from the CDSE

    Parameters
    ----------
    scene : str
        Scene of interest. E.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD
    download_folder : Path
        Folder to download file to.
    make_folder : bool, optional
        Make non-existing folders, by default True
    unzip : bool, optional
        Unzip the downloaded file, by default True
    cdse_login : str | None, optional
        Login for the ASF, by default None. If not specified env variable
        CDSE_LOGIN will be used.
    cdse_pass : str | None, optional
        Login for the ASF, by default None. If not specified env variable
        CDSE_PASSWORD will be used.

    Returns
    -------
    tuple[str,dict]
        Path to downloaded scene and dict of metadata

    Raises
    ------
    MissingCredentialsError
        Required credentials are not set
    NonSingleSceneResultError
        0, or more than one SLC result is found.
    SceneDownloadError
        Error with download
    """

    # Authenticate. If credentials not supplied search the environment variables
    if cdse_login is None and cdse_pass is None:
        cdse_login = os.getenv("CDSE_LOGIN")
        cdse_pass = os.getenv("CDSE_PASSWORD")
        if not cdse_login or cdse_pass:
            err_string = (
                "Not all credentials supplied. Please provide a cdse_login and cdse_pass "
                "or set the CDSE_LOGIN and CDSE_PASSWORD environment variables"
            )
            MissingCredentialsError(err_string)

    if make_folder:
        os.makedirs(download_folder, exist_ok=True)

    # search for scene on CDSE
    cdse_scenes_metadata = query_scene_from_cdse(scene)

    if len(cdse_scenes_metadata) != 1:
        raise NonSingleSceneResultError(
            f"Expected 1 scene, found {len(cdse_scenes_metadata)} for scene id : {scene}"
        )
    else:
        cdse_scene_metadata = cdse_scenes_metadata[0]

    scene_zip_path = Path(download_folder) / f"{scene}.SAFE.zip"
    scene_safe_path = scene_zip_path.with_suffix("")

    # download zip if safe file doesn't exist or zip doesn't exist
    if scene_safe_path.exists() and unzip:
        logger.info(f"Skipping download, unzipped scene exists at : {scene_safe_path}")
    elif scene_zip_path.exists():
        logger.info(f"Skipping download, zipped scene exists at : {scene_zip_path}")
    else:
        logger.info(f"Downloading : {scene}.zip")
        try:
            list(
                download_features(
                    cdse_scenes_metadata,
                    download_folder,
                    {
                        "concurrency": 1,
                        "monitor": StatusMonitor(),
                        "credentials": Credentials(cdse_login, cdse_pass),
                    },
                )
            )
        except:
            logger.error(
                "An error occurred while running the download command", exc_info=True
            )
            raise SceneDownloadError

    if unzip and not os.path.exists(scene_safe_path):
        logger.info(f"unzipping scene to {scene_safe_path}")
        with zipfile.ZipFile(scene_zip_path, "r") as zip_ref:
            zip_ref.extractall(download_folder)
        return scene_safe_path, cdse_scene_metadata
    elif scene_safe_path.exists() and unzip:
        return scene_safe_path, cdse_scene_metadata
    else:
        return scene_zip_path, cdse_scene_metadata


@log_timing
def download_scene_from_aus_cop_hub(
    scene: str,
    download_folder: Path,
    make_folder: bool = True,
    unzip: bool = True,
    aus_cop_hub_login: str | None = None,
    aus_cop_hub_pass: str | None = None,
    aus_cop_hub_client_id: str | None = None,
    aus_cop_hub_client_secret: str | None = None,
    service: str = "https://catalogue.copernicus.gov.au/odata/v1",
    token_url: str = "https://auth.copernicus.gov.au/realms/gss/protocol/openid-connect/token",
    pygssearch_conda_env_path: str | Path = None,
) -> tuple[Path, dict]:
    """Download the scene and query associated metadata from the Copernicus
    Australasia Regional Data Hub. Function makes use of pygssearch -
    https://pypi.org/project/pygssearch/ which is installed in a separate conda environment
    and called in a subprocess due to package conflicts. The path to the conda environment
    can be set in the function or as an environment variable (e.g. defined in the isce3_rtc/Dockerfile).

    Parameters
    ----------
    scene : str
        scene name. e.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD
    download_folder : Path
        Folder where the scene should be downloaded to
    make_folder : bool, optional
        Make non-existing folders, by default True
    unzip : bool, optional
        Unzip the downloaded file, by default True
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
    pygssearch_conda_env_path: str | Path, optional
        Path to the conda environment containing an installation of pygssearch that will be called in a
        subprocess. If not specified, If not specified env variable PYGSSEARCH_CONDA_ENV will be used.

    Returns
    -------
    tuple[Path, dict]
        Path to the downloaded scene and the associated metadata.

    Raises
    ------
    MissingCredentialsError
        Required credentials are not set
    NonSingleSceneResultError
        Could not find exactly 1 scene
    RuntimeError
        Error with download from the subprocess.
    SceneDownloadError
        Error with download.
    """
    # Fallback to environment variables if arguments are not provided
    aus_cop_hub_login = aus_cop_hub_login or os.getenv("AUS_COP_HUB_LOGIN")
    aus_cop_hub_pass = aus_cop_hub_pass or os.getenv("AUS_COP_HUB_PASSWORD")
    aus_cop_hub_client_id = aus_cop_hub_client_id or os.getenv("AUS_COP_HUB_CLIENT_ID")
    aus_cop_hub_client_secret = aus_cop_hub_client_secret or os.getenv(
        "AUS_COP_HUB_CLIENT_SECRET"
    )
    pygssearch_conda_env_path = pygssearch_conda_env_path or os.getenv(
        "PYGSSEARCH_CONDA_ENV"
    )

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

    if make_folder:
        os.makedirs(download_folder, exist_ok=True)

    # use the pygssearch command line tool to query scene metadata and then download
    base_query = (
        f"conda run -p {pygssearch_conda_env_path} "
        f"pygssearch --service {service} "
        f"--username {aus_cop_hub_login} "
        f"--password {aus_cop_hub_pass} "
        f"--token_url {token_url} "
        f"--client_id {aus_cop_hub_client_id} "
        f"--client_secret {aus_cop_hub_client_secret} "
        f"--name {scene} "
    )

    # structure query for metadata
    metadata_cmd = base_query + f"--format _ " + f"--attributes "
    logger.info(f"Using pygssearch to query Aus Cop Hub for scene metadata")

    process = subprocess.Popen(
        metadata_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        # convert the pygssearch result to a python object
        # an emtpy list is returned if no results found, else list of jsons
        output, _ = process.communicate()
        sanitised_output = re.sub(
            r"(--?(client_secret|password)[=\s]+)\S+", r"\1****", output
        )
        aus_cophub_scenes_metadata = ast.literal_eval(sanitised_output)
    except Exception as e:
        logger.error(
            "Could not convert Aus Cop Hub query response to list of JSON data. Check credentials and request.",
        )
        raise

    # ensure only one slc found
    if len(aus_cophub_scenes_metadata) != 1:
        raise NonSingleSceneResultError(
            f"Expected 1 scene, found {len(aus_cophub_scenes_metadata)} for scene id : {scene}"
        )
    else:
        aus_cophub_scene_metadata = aus_cophub_scenes_metadata[0]
        logger.info(f"Scene metadata found")

    # create query for download
    download_cmd = base_query + "--download " + f"--output {download_folder}"

    # make scene .SAFE and zip paths
    scene_zip_path = Path(download_folder) / f"{scene}.zip"
    scene_safe_path = scene_zip_path.with_suffix(".SAFE")

    # download zip if SAFE file doesn't exist or zip doesn't exist
    if scene_safe_path.exists() and unzip:
        logger.info(f"Skipping download, unzipped scene exists at : {scene_safe_path}")
    elif scene_zip_path.exists():
        logger.info(f"Skipping download, zipped scene exists at : {scene_zip_path}")
    else:
        logger.info(
            f"Using pygssearch download scene from Aus Cop Hub to: {download_folder}"
        )

        try:
            logger.info(f"Download in progress...")
            process = subprocess.Popen(
                download_cmd,
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
            raise SceneDownloadError

    # construct the download url and add it to the metadata
    aus_cophub_scene_metadata["url"] = (
        f'{service}/Products({aus_cophub_scene_metadata["Id"]})'
    )

    if unzip and not os.path.exists(scene_safe_path):
        logger.info(f"unzipping scene to {scene_safe_path}")
        with zipfile.ZipFile(scene_zip_path, "r") as zip_ref:
            zip_ref.extractall(download_folder)
        return scene_safe_path, aus_cophub_scene_metadata
    elif scene_safe_path.exists() and unzip:
        return scene_safe_path, aus_cophub_scene_metadata
    else:
        return scene_zip_path, aus_cophub_scene_metadata


@log_timing
def download_scene_from_preference_list(
    scene_data_source_preferences: list,
    scene: str,
    download_folder: str | Path,
    unzip: bool = True,
) -> tuple[Path, shapely.geometry.shape, str]:
    f"""Download the scene from a list of preferenced data sources

    Parameters
    ----------
    scene_data_source_preferences : list
        List of data sources to download the scene. Must be any of {VALID_SCENE_DATA_SOURCES}
    scene : str
        scene name. e.g. 
    download_folder : str | Path
        Location to download the scene
    unzip: bool
        whether to unzip the downloaded scene

    Returns
    -------
    tuple[Path, shapely.geometry.shape, str]
        The Path to the downloaded scene, the scene geometry and scene url

    Raises
    ------
    ValueError
        The list of preferences is not valid
    e
        
    """
    if not all(
        [ds in VALID_SCENE_DATA_SOURCES for ds in scene_data_source_preferences]
    ):
        raise ValueError(
            f"--scene-data-source valid values are {VALID_SCENE_DATA_SOURCES}"
        )

    for i, data_source in enumerate(scene_data_source_preferences):
        logger.info(
            f"Attempting to download scene from preference {i+1} of {len(scene_data_source_preferences)} : {data_source}"
        )
        try:
            if data_source == "ASF":
                # download the SLC and get scene metadata from asf
                SCENE_PATH, asf_scene_metadata = download_scene_from_asf(
                    scene, download_folder, unzip=unzip
                )
                scene_polygon = shapely.geometry.shape(asf_scene_metadata.geometry)
                scene_url = asf_scene_metadata.properties["url"]
                break

            elif data_source == "CDSE":
                SCENE_PATH, cdse_scene_metadata = download_scene_from_cdse(
                    scene, download_folder, unzip=unzip
                )
                scene_polygon = shapely.geometry.shape(cdse_scene_metadata["geometry"])
                scene_url = cdse_scene_metadata["properties"]["services"]["download"][
                    "url"
                ]
                break

            elif data_source == "AUS_COP_HUB":
                SCENE_PATH, aus_cophub_scenes_metadata = (
                    download_scene_from_aus_cop_hub(scene, download_folder, unzip=unzip)
                )
                scene_polygon = shapely.geometry.shape(
                    aus_cophub_scenes_metadata["GeoFootprint"]
                )
                scene_url = aus_cophub_scenes_metadata["url"]
                break
        except Exception as e:
            logger.error(
                f"Could not download scene from preference {i+1} of {len(scene_data_source_preferences)} : {data_source}",
                exc_info=True,
            )
            if data_source == scene_data_source_preferences[-1]:
                raise SceneDownloadError(
                    f"Scene could not be downloaded from any data source provided : {scene_data_source_preferences}"
                ) from e

    logger.info(f"Scene successfully downloaded from: {data_source}")
    return SCENE_PATH, scene_polygon, scene_url
