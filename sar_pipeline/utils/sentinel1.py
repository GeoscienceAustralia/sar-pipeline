import re

# Taken from https://sentiwiki.copernicus.eu/web/s1-products#S1Products-SARNamingConventionS1-Products-SAR-Naming-Convention
SENTINEL_1_ID_PATTERN = (
    r"^S1[ABC]_"  # MMM: S1A, S1B, S1C
    r"(S1|S2|S3|S4|S5|S6|IW|EW|WV|EN|N[1-6]|Z[IEW1-6])_"  # BB: Beam identifiers
    r"(RAW|SLC|GRD|OCN|ETA)"  # TTT: Product Type
    r"[FHM_]_"  # R: Resolution class
    r"[012A]"  # L: Processing level
    r"[SANCX]"  # F: Product class
    r"(SH|SV|DH|DV|HH|HV|VV|VH)_"  # PP: Polarisation
    r"\d{8}T\d{6}_"  # Start datetime
    r"\d{8}T\d{6}_"  # Stop datetime
    r"\d{6}_"  # Orbit number (000000–999999)
    r"(?!000000)[A-F0-9]{6}_"  # Data-take ID: non-zero hex
    r"[A-F0-9]{4}"  # CRC16 and extension
)

SENTINEL_1_FILE_PATTERN = SENTINEL_1_ID_PATTERN + r"\.SAFE$"


def is_s1_id(id: str) -> bool:
    match = re.compile(SENTINEL_1_ID_PATTERN).fullmatch(id)
    if match:
        return True
    else:
        return False


def is_s1_filename(filename: str) -> bool:
    match = re.compile(SENTINEL_1_FILE_PATTERN).fullmatch(filename)
    if match:
        return True
    else:
        return False
