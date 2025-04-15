import dataclasses
from datetime import datetime
from pathlib import Path, PurePath
import pytest

from sar_pipeline.preparation.etad import parse_etad_file_dates, extract_etad_correction


@dataclasses.dataclass
class SceneEtadPair:
    scene: str
    etad: str
    etad_start_date: datetime
    etad_stop_date: datetime


etad_1 = SceneEtadPair(
    "S1A_IW_SLC__1SDV_20230818T195223_20230818T195250_049934_0601BA_AE0C",
    "S1A_IW_ETA__AXDV_20230818T195223_20230818T195250_049934_0601BA_4281",
    datetime(2023, 8, 18, 19, 52, 23),
    datetime(2023, 8, 18, 19, 52, 50),
)

etad_2 = SceneEtadPair(
    "S1A_IW_SLC__1SDV_20230911T195224_20230911T195251_050284_060DB2_CC96",
    "S1A_IW_ETA__AXDV_20230911T195224_20230911T195251_050284_060DB2_4CFD",
    datetime(2023, 9, 11, 19, 52, 24),
    datetime(2023, 9, 11, 19, 52, 51),
)

etad_3 = SceneEtadPair(
    "S1A_IW_SLC__1SDV_20240601T195221_20240601T195248_054134_06953D_BA35",
    "S1A_IW_ETA__AXDV_20240601T195221_20240601T195248_054134_06953D_1587",
    datetime(2024, 6, 1, 19, 52, 21),
    datetime(2024, 6, 1, 19, 52, 48),
)

etad_list = [etad_1, etad_2, etad_3]


@pytest.mark.parametrize("scene_etad_pair", etad_list)
def test_parse_etad_file_dates(scene_etad_pair: SceneEtadPair):
    date_tuple = (scene_etad_pair.etad_start_date, scene_etad_pair.etad_stop_date)
    assert parse_etad_file_dates(scene_etad_pair.etad) == date_tuple
