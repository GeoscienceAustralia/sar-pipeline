from datetime import datetime
import re
from dataclasses import dataclass
from typing import Literal, get_args

# Taken from https://sentiwiki.copernicus.eu/web/s1-products#S1Products-SARNamingConventionS1-Products-SAR-Naming-Convention
Mission = Literal["S1A", "S1B", "S1C"]
ModeBeam = Literal[
    "S1",
    "S2",
    "S3",
    "S4",
    "S5",
    "S6",
    "IW",
    "EW",
    "WV",
    "SM",
    "N1",
    "N2",
    "N3",
    "N4",
    "N5",
    "N6",
    "Z1",
    "Z2",
    "Z3",
    "Z4",
    "Z5",
    "Z6",
    "ZI",
    "ZE",
    "ZW",
]
ProductType = Literal["RAW", "SLC", "GRD", "OCN", "ETA"]
Resolution = Literal["F", "M", "H", "_"]
ProcessingLevel = Literal["0", "1", "2", "A"]
ProductClass = Literal["S", "A", "N", "C", "X"]
Polarisation = Literal["SH", "SV", "DH", "DV", "HH", "HV", "VV", "VH"]


@dataclass
class Sentinel1SceneId:
    mission: str
    mode_beam: str
    product_type: str
    resolution: str
    processing_level: str
    product_class: str
    polarisation: str
    start_datetime: datetime
    stop_datetime: datetime
    orbit_number: str
    data_take: str
    uid: str


SENTINEL_1_ID_PATTERN = (
    r"(S1[ABC])_"  # MMM: S1A, S1B, S1C
    r"(S1|S2|S3|S4|S5|S6|IW|EW|WV|EN|N[1-6]|Z[IEW1-6])_"  # BB: Beam identifiers
    r"(RAW|SLC|GRD|OCN|ETA)"  # TTT: Product Type
    r"([FHM_])_"  # R: Resolution class
    r"([012A])"  # L: Processing level
    r"([SANCX])"  # F: Product class
    r"(SH|SV|DH|DV|HH|HV|VV|VH)_"  # PP: Polarisation
    r"(\d{8}T\d{6})_"  # Start datetime
    r"(\d{8}T\d{6})_"  # Stop datetime
    r"(\d{6})_"  # Orbit number (000000–999999)
    r"((?!000000)[A-F0-9]{6})_"  # Data-take ID: non-zero hex
    r"([A-F0-9]{4})"  # CRC16 and extension
)

SENTINEL_1_FILE_PATTERN = SENTINEL_1_ID_PATTERN + r"\.SAFE"


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


def extract_metadata_from_s1_id(id: str) -> Sentinel1SceneId:

    if is_s1_id(id) or is_s1_filename(id):
        match = re.compile(SENTINEL_1_ID_PATTERN).match(id)

        if match is not None:
            metadata = Sentinel1SceneId(
                mission=match.group(1),
                mode_beam=match.group(2),
                product_type=match.group(3),
                resolution=match.group(4),
                processing_level=match.group(5),
                product_class=match.group(6),
                polarisation=match.group(7),
                start_datetime=datetime.strptime(match.group(8), "%Y%m%dT%H%M%S"),
                stop_datetime=datetime.strptime(match.group(9), "%Y%m%dT%H%M%S"),
                orbit_number=match.group(10),
                data_take=match.group(11),
                uid=match.group(12),
            )
        else:
            raise ValueError(
                f"ID: {id} was recognised as a valid ID/filename, but metadata match was unsuccessful. Check SENTINEL_1_ID_PATTERN in sar_pipeline/utils/sentinel1.py"
            )
    else:
        raise ValueError(
            f"ID: {id} is not a valid ID/filename. Check SENTINEL_1_ID_PATTERN in sar_pipeline/utils/sentinel1.py"
        )

    return metadata


def get_mission_from_scene_id(id: str) -> str:

    id_metadata = extract_metadata_from_s1_id(id)
    mission = id_metadata.mission

    if mission in get_args(Mission):
        return mission
    else:
        raise ValueError(
            f"Mission value {mission} is not valid. Valid missions are {get_args(Mission)}. Check the input ID."
        )


def get_mode_from_scene_id(id: str) -> str:

    id_metadata = extract_metadata_from_s1_id(id)
    mode_beam = id_metadata.mode_beam

    if mode_beam in get_args(ModeBeam):
        return mode_beam
    else:
        raise ValueError(
            f"Mode beam value {mode_beam} is not valid. Valid mode beams are {get_args(ModeBeam)}. Check the input ID."
        )


def get_product_type_from_scene_id(id: str) -> str:

    id_metadata = extract_metadata_from_s1_id(id)
    product_type = id_metadata.product_type

    if product_type in get_args(ProductType):
        return product_type
    else:
        raise ValueError(
            f"Product type value {product_type} is not valid. Valid product types are {get_args(ProductType)}. Check the input ID."
        )


def get_dates_from_scene_id(id: str) -> tuple[datetime, datetime]:

    id_metadata = extract_metadata_from_s1_id(id)
    start_date = id_metadata.start_datetime
    stop_date = id_metadata.stop_datetime

    return (start_date, stop_date)


def get_polarisation_list_from_scene_id(id: str) -> list[str]:
    id_metadata = extract_metadata_from_s1_id(id)
    pol_string_to_pol_list = {
        "SH": ["HH"],
        "SV": ["VV"],
        "DH": ["HH", "HV"],
        "DV": ["VV", "VH"],
        "HH": ["HH"],
        "HV": ["HV"],
        "VV": ["VV"],
        "VH": ["VH"],
    }
    return pol_string_to_pol_list[id_metadata.polarisation]
