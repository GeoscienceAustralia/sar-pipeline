from datetime import datetime, timedelta
import logging
from pathlib import Path
import requests
import zipfile


from s1etad_tools.cli.slc_correct import s1etad_slc_correct_main
from sar_pipeline.nci.preparation.scenes import parse_scene_file_dates

logger = logging.getLogger(__name__)


def parse_etad_file_dates(etad_id: str) -> tuple[datetime, datetime]:

    # ETAD filename has same format as scene, so run scene file dates function
    start_date, stop_date = parse_scene_file_dates(etad_id)

    return (start_date, stop_date)


def get_cdse_access_token(username, password) -> str:

    data = {
        "grant_type": "password",
        "username": f"{username}",
        "password": f"{password}",
        "client_id": "cdse-public",
    }

    response = requests.post(
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
        data=data,
    )

    access_token = response.json()["access_token"]

    return access_token


def find_etad_for_scene_on_cdse(scene):

    scene_start, _ = parse_scene_file_dates(scene)

    # Buffer start and end by a few seconds to ensure correct ETAD file is found
    buffer_seconds = 2
    start_query_min = scene_start - timedelta(seconds=buffer_seconds)
    start_query_max = scene_start + timedelta(seconds=buffer_seconds)

    # Convert to string format expected for CDSE OData query
    ODATA_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.000Z"
    start_query_min = start_query_min.strftime(ODATA_TIME_FORMAT)
    start_query_max = start_query_max.strftime(ODATA_TIME_FORMAT)

    filter_queries = [
        "Collection/Name eq 'SENTINEL-1'",
        f"ContentDate/Start gt {start_query_min}",
        f"ContentDate/Start lt {start_query_max}",
        f"contains(Name,'ETA')",
    ]
    # CDSE filter has format "{query 1} and {query 2} and ... {query n}"
    query_string = " and ".join(filter_queries)

    search_url = f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter={query_string}&$top=100"
    search_results = requests.get(search_url).json()["value"]

    # Only one ETAD file should exist per scene
    if len(search_results) == 1:
        etad_search_result = search_results[0]
    elif len(search_results) == 0:
        raise ValueError(f"No ETAD products found. Scene start date: {scene_start}")
    elif len(search_results) > 1:
        raise ValueError(
            f"{len(search_results)} ETAD products found, which is too many. Review files: {[result['Name'] for result in search_results]}"
        )

    return etad_search_result


def download_etad_for_scene_from_cdse(
    scene: str, etad_dir: Path, cdse_user: str, cdse_password: str, unzip: bool = False
):
    logger.info("Searching Copernicus Dataspace for ETAD file")
    etad_search_result = find_etad_for_scene_on_cdse(scene)
    etad_id = etad_search_result["Id"]
    etad_name = etad_search_result["Name"]
    etad_filename = etad_name + ".zip"  # {etad_name}.SAFE.zip

    # Prepare for download
    access_token = get_cdse_access_token(cdse_user, cdse_password)
    download_url = (
        f"https://zipper.dataspace.copernicus.eu/odata/v1/Products({etad_id})/$value"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    session = requests.Session()
    session.headers.update(headers)
    response = session.get(download_url, headers=headers, stream=True)
    etad_zip = etad_dir / etad_filename

    # Perform download
    if not etad_zip.exists():
        logger.info(f"Downloading ETAD to: {etad_zip}")
        with open(f"{etad_zip}", "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
    else:
        logger.info("ETAD Product already downloaded")

    if unzip:
        etad_safe = etad_zip.with_suffix("")  # Removes .zip suffix, leaving .SAFE
        if not etad_safe.exists():
            logger.info(f"Unzipping to : {etad_safe}")
            archive = zipfile.ZipFile(etad_zip, "r")
            archive.extractall(etad_dir)
            archive.close()

    return etad_zip if not unzip else etad_safe


def find_etad_for_scene(scene: str, etad_dir: Path):

    buffer_seconds = 2
    scene_start, _ = parse_scene_file_dates(scene)
    start_query_min = scene_start - timedelta(seconds=buffer_seconds)
    start_query_max = scene_start + timedelta(seconds=buffer_seconds)

    etad = None
    for etad_file in etad_dir:
        etad_start, _ = parse_etad_file_dates(etad_file)
        if (etad_start >= start_query_min) and (etad_start <= start_query_max):
            etad = etad_file
            logger.info(f"Found ETAD for scene: {etad}")
            break
    if etad is None:
        raise RuntimeError(
            f"No ETAD correction file found for scene: {scene}. Download one first."
        )
    return etad


def apply_etad_correction(scene: Path, etad: Path, outdir: Path, nthreads: int = 4):

    # Validate that input scene and etad are .SAFE directiories
    if not (scene.is_dir() and scene.suffix == ".SAFE"):
        raise TypeError(
            f"{scene} is not a .SAFE directory. If it is a compressed file, extract it before passing to this function."
        )

    if not (etad.is_dir() and etad.suffix == ".SAFE"):
        raise TypeError(
            f"{etad} is not a .SAFE directory. If it is a compressed file, extract it before passing to this function."
        )

    # Create directory for corrected product
    if not outdir.exists():
        outdir.mkdir(parents=True)

    corrected_scene = scene_corrected_safe = outdir / scene.name

    # If corrected scene does not exist as a .SAFE directory, run the correction
    if not corrected_scene.exists():
        logger.info("Correcting SLC with ETAD product")

        # Apply corrections using .SAFE files
        s1etad_slc_correct_main(
            s1_product=scene,
            etad_product=etad,
            outdir=outdir,
            nthreads=nthreads,
            order=0,
        )  # using the default 1 introduces a bias of about -0.5 dB.
    else:
        logger.info(f"ETAD corrected product already exists: {scene_corrected_safe}")

    return scene_corrected_safe
