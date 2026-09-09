import pooch

# Where data will be stored within the operating system's cache directory
CACHE_DIR = "sar_pipeline"

# Base URL for data on AWS
BASE_URL = "https://data.dev.dea.ga.gov.au/projects/s1_nrb/"


# BURST DATABASE
S1_NRB_BURST_DB = pooch.create(
    path=pooch.os_cache(CACHE_DIR),
    base_url=BASE_URL + "burst_db/0.9.0/",
    registry={
        "opera-burst-bbox-only.sqlite3": None,
    },
)


def fetch_burst_db() -> str:
    return S1_NRB_BURST_DB.fetch("opera-burst-bbox-only.sqlite3")
