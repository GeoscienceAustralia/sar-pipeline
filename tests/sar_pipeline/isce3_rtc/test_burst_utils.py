from click.testing import CliRunner
from dataclasses import dataclass
from pathlib import Path
import pytest
from sar_pipeline.pipelines.isce3_rtc.utils.burst_utils import (
    check_burst_product_h5_exists_in_s3,
    get_burst_info_for_scene_from_cdse,
    get_burst_info_and_scene_poly_from_file,
    resolve_burst_info,
    get_burst_candidates,
    CDSEBurstAPIError,
)
import requests

import logging
from datetime import datetime

logging.basicConfig(
    level=logging.DEBUG,  # or INFO
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[2]
TEST_WORKSPACE = CURRENT_DIR / Path("data")


# Existing products for testing are stored in the BENCHMARK_S3_PROJECT_FOLDER
# These can be created in the test_full_docker_workflow_run.py script
from settings import (
    TEST_1_SCENE,
    TEST_1_BURST,
    TEST_1_BURST_ST,
    TEST_1_POLS,
    TEST_S3_BUCKET,
    BENCHMARK_S3_PROJECT_FOLDER,
)


@dataclass
class BurstProduct:
    scene: str
    product: str
    burst_id_list: list
    burst_st_list: list[datetime]
    burst_polarisations: list
    s3_bucket: str
    s3_project_folder: str
    collection_number: int
    dem_type: str
    static_layer_validity_start_date: int
    make_existing_products: bool
    EXISTS: bool


TEST_NON_EXISTING_RTC_S1 = BurstProduct(
    scene="S1A_IW_SLC__1SDV_20221202T104303_20221202T104332_046151_058667_0E6A",
    product="RTC_S1",
    burst_id_list=["t054_115777_iw1"],
    burst_st_list=[
        datetime.strptime("2022-12-02T10:43:11.380294Z", "%Y-%m-%dT%H:%M:%S.%fZ")
    ],
    burst_polarisations=["VV", "VH"],
    s3_bucket=TEST_S3_BUCKET,
    s3_project_folder=BENCHMARK_S3_PROJECT_FOLDER,
    collection_number=1,
    dem_type="cop_glo30",
    static_layer_validity_start_date=20140403,
    make_existing_products=False,
    EXISTS=False,
)

TEST_EXISTING_RTC_S1 = BurstProduct(
    scene=TEST_1_SCENE,
    product="RTC_S1",
    burst_id_list=[TEST_1_BURST],
    burst_st_list=[datetime.strptime(TEST_1_BURST_ST, "%Y-%m-%dT%H:%M:%S.%fZ")],
    burst_polarisations=TEST_1_POLS,
    s3_bucket=TEST_S3_BUCKET,
    s3_project_folder=BENCHMARK_S3_PROJECT_FOLDER,
    collection_number=1,
    dem_type="REMA_32",
    static_layer_validity_start_date=20140403,
    make_existing_products=False,
    EXISTS=True,
)

TEST_NON_EXISTING_RTC_S1_STATIC = BurstProduct(
    scene="S1A_IW_SLC__1SDV_20221202T104303_20221202T104332_046151_058667_0E6A",
    product="RTC_S1_STATIC",
    burst_id_list=["t054_115777_iw1"],
    burst_st_list=[
        datetime.strptime("2022-12-02T10:43:11.380294Z", "%Y-%m-%dT%H:%M:%S.%fZ")
    ],
    burst_polarisations=["VV", "VH"],
    s3_bucket=TEST_S3_BUCKET,
    s3_project_folder=BENCHMARK_S3_PROJECT_FOLDER,
    collection_number=1,
    dem_type="cop_glo30",
    static_layer_validity_start_date=20140403,
    make_existing_products=False,
    EXISTS=False,
)

TEST_EXISTING_RTC_S1_STATIC = BurstProduct(
    scene=TEST_1_SCENE,
    product="RTC_S1_STATIC",
    burst_id_list=[TEST_1_BURST],
    burst_st_list=[datetime.strptime(TEST_1_BURST_ST, "%Y-%m-%dT%H:%M:%S.%fZ")],
    burst_polarisations=TEST_1_POLS,
    s3_bucket=TEST_S3_BUCKET,
    s3_project_folder=BENCHMARK_S3_PROJECT_FOLDER,
    collection_number=1,
    dem_type="REMA_32",
    static_layer_validity_start_date=20140403,
    make_existing_products=False,
    EXISTS=True,
)

TEST_BURST_PRODUCT_EXIST_CASES = [
    TEST_NON_EXISTING_RTC_S1,
    TEST_EXISTING_RTC_S1,
    TEST_NON_EXISTING_RTC_S1_STATIC,
    TEST_EXISTING_RTC_S1_STATIC,
]


@pytest.mark.parametrize("test_run", TEST_BURST_PRODUCT_EXIST_CASES)
def test_check_burst_product_h5_exists_in_s3(test_run):

    # we expect the product to already exist and therefore exit early
    # as the processing does not need to occur
    if test_run.EXISTS:
        with pytest.raises(SystemExit) as e:
            check_burst_product_h5_exists_in_s3(
                product=test_run.product,
                burst_id_list=test_run.burst_id_list,
                burst_st_list=test_run.burst_st_list,
                burst_polarisations=test_run.burst_polarisations,
                s3_bucket=test_run.s3_bucket,
                s3_project_folder=test_run.s3_project_folder,
                collection_number=test_run.collection_number,
                dem_type=test_run.dem_type,
                static_layer_validity_start_date=test_run.static_layer_validity_start_date,
                make_existing_products=test_run.make_existing_products,
                early_exit=True,
            )
        assert e.type == SystemExit
        assert e.value.code == 100

    # the product does not already exist, we expect to return the burst
    # in the list to process
    elif not test_run.EXISTS:
        burst_id_list_to_process = check_burst_product_h5_exists_in_s3(
            product=test_run.product,
            burst_id_list=test_run.burst_id_list,
            burst_st_list=test_run.burst_st_list,
            burst_polarisations=test_run.burst_polarisations,
            s3_bucket=test_run.s3_bucket,
            s3_project_folder=test_run.s3_project_folder,
            collection_number=test_run.collection_number,
            dem_type=test_run.dem_type,
            static_layer_validity_start_date=test_run.static_layer_validity_start_date,
            make_existing_products=test_run.make_existing_products,
            early_exit=True,
        )
        assert burst_id_list_to_process == test_run.burst_id_list


TEST_DATA = CURRENT_DIR.parent / "data"
TEST_SAFE = (
    TEST_DATA
    / "scenes"
    / "S1A_IW_SLC__1SDV_20200511T135117_20200511T135144_032518_03C421_7768.zip"
)
TEST_ORBIT = (
    TEST_DATA
    / "orbits"
    / "S1A_OPER_AUX_POEORB_OPOD_20210318T120818_V20200510T225942_20200512T005942.EOF"
)


def test_burst_info_from_safe_matches_cdse():
    """Burst ids and start times read from the SAFE must match the CDSE Bursts API."""
    cdse_burst_info = get_burst_info_for_scene_from_cdse(TEST_SAFE.stem)
    file_burst_info, _ = get_burst_info_and_scene_poly_from_file(
        scene_path=TEST_SAFE, orbit_path=TEST_ORBIT, swath_list=[1, 2, 3]
    )
    assert set(file_burst_info) == set(cdse_burst_info)
    for burst_id, file_entry in file_burst_info.items():
        assert file_entry["azimuth_time"] == cdse_burst_info[burst_id]["azimuth_time"]
        assert file_entry["start_time"] == cdse_burst_info[burst_id]["start_time"]


def test_cdse_burst_api_timeout_raises_clear_error(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(requests, "get", timeout)
    with pytest.raises(CDSEBurstAPIError, match="timed out or is unavailable"):
        get_burst_info_for_scene_from_cdse(TEST_SAFE.stem)


@pytest.mark.parametrize(
    "cdse_burst_info, file_burst_info, expected",
    [
        ({"t1": "cdse"}, {"t1": "file"}, {"t1": "cdse"}),  # ids match -> CDSE
        ({"t1": "cdse"}, {"t2": "file"}, {"t2": "file"}),  # ids differ -> file
        (None, {"t1": "file"}, {"t1": "file"}),  # CDSE down -> file
    ],
)
def test_resolve_burst_info(cdse_burst_info, file_burst_info, expected):
    assert resolve_burst_info(cdse_burst_info, file_burst_info) == expected


BURST_INFO = {
    "t1": {"azimuth_time": datetime(2020, 1, 1, 0, 0, 1)},
    "t2": {"azimuth_time": datetime(2020, 1, 1, 0, 0, 2)},
}


@pytest.mark.parametrize(
    "burst_id_list, expected_ids",
    [(None, ["t1", "t2"]), ("", ["t1", "t2"]), ("t2", ["t2"])],
)
def test_get_burst_candidates(burst_id_list, expected_ids):
    ids, sts = get_burst_candidates(BURST_INFO, burst_id_list)
    assert ids == expected_ids
    assert sts == [BURST_INFO[b]["azimuth_time"] for b in expected_ids]


def test_get_burst_candidates_raises_for_burst_not_in_scene():
    with pytest.raises(ValueError, match="t3"):
        get_burst_candidates(BURST_INFO, "t1 t3")
