from click.testing import CliRunner
from dataclasses import dataclass
from pathlib import Path
import pytest
from sar_pipeline.pipelines.isce3_rtc.utils.burst_utils import (
    check_burst_product_h5_exists_in_s3,
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
