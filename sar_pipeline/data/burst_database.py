from typing import Literal

import pooch

# Where data will be stored within the operating system's cache directory
CACHE_DIR = "sar_pipeline"

# Base URL for data on AWS
BASE_URL = "https://dea-public-data-dev.s3.ap-southeast-2.amazonaws.com/projects/s1_nrb/"

# Burst database version. Keep in sync with BURST_DB_VERSION_TAG in Docker/isce3_rtc/Dockerfile
BURST_DB_VERSION = "0.18.0"


# BURST DATABASE
# cached by version so a new version never reuses an old file with the same name
S1_NRB_BURST_DB = pooch.create(
    path=pooch.os_cache(CACHE_DIR) / "burst_db" / BURST_DB_VERSION,
    base_url=BASE_URL + f"burst_db/{BURST_DB_VERSION}/",
    registry={
        "opera-iw-burst-bbox-only.sqlite3": None,
        "opera-ew-burst-bbox-only.sqlite3": None,
    },
)


def fetch_burst_db(mode: Literal["IW", "EW"] = "IW") -> str:
    """Fetch the burst database for the acquisition mode, downloading it if not cached.

    Parameters
    ----------
    mode : Literal["IW", "EW"], optional
        Sentinel-1 acquisition mode of the burst database, by default "IW"

    Returns
    -------
    str
        Local path to the burst database sqlite file
    """
    burst_db_path = S1_NRB_BURST_DB.fetch(
        f"opera-{mode.lower()}-burst-bbox-only.sqlite3"
    )
    return burst_db_path
