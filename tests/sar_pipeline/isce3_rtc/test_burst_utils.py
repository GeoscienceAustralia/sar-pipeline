from click.testing import CliRunner
from dataclasses import dataclass
from pathlib import Path
import pytest
from sar_pipeline.pipelines.isce3_rtc.utils.burst_utils import (
    check_burst_product_h5_exists_in_s3,
    get_burst_info_for_scene_from_cdse,
    get_burst_info_and_scene_poly_from_file,
    assert_burst_info_equivalent
)

import logging
from datetime import datetime

logging.basicConfig(
    level=logging.DEBUG,  # or INFO
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[2]
TEST_WORKSPACE = CURRENT_DIR.parent / Path("data")


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


# Test the burst information from the CDSE and that read directly from
# A SAFE file are equivalent

SAFE_FILE_PATHS = [
    TEST_WORKSPACE / "scenes" / "S1A_EW_SLC__1SDH_20220330T185405_20220330T185511_042554_051380_3E95.zip",
    TEST_WORKSPACE / "scenes" / "S1A_IW_SLC__1SDV_20200511T135117_20200511T135144_032518_03C421_7768.zip",
] 

SAFE_TO_ORBIT_FILE = {
    SAFE_FILE_PATHS[0]: TEST_WORKSPACE / "orbits" / "S1A_OPER_AUX_POEORB_OPOD_20220419T081726_V20220329T225942_20220331T005942.EOF",
    SAFE_FILE_PATHS[1]: TEST_WORKSPACE / "orbits" / "S1A_OPER_AUX_POEORB_OPOD_20210318T120818_V20200510T225942_20200512T005942.EOF",
}


@pytest.mark.parametrize("safe_file_path", SAFE_FILE_PATHS)
def test_burst_info_matches_cdse(safe_file_path):
    """Compare burst info from the CDSE API against burst info loaded
    directly from a local SAFE file, for the same scene."""

    orbit_path = SAFE_TO_ORBIT_FILE[safe_file_path]
    scene_id = safe_file_path.stem  # strips .zip
    sensor_mode = scene_id.split("_")[1]
    swath_list = {"IW": [1, 2, 3], "EW": [1, 2, 3, 4, 5]}[sensor_mode]

    cdse_burst_info = get_burst_info_for_scene_from_cdse(scene_id)

    file_burst_info, _ = get_burst_info_and_scene_poly_from_file(
        scene_path=safe_file_path,
        orbit_path=orbit_path,
        swath_list=swath_list,
    )

    assert_burst_info_equivalent(cdse_burst_info, file_burst_info)