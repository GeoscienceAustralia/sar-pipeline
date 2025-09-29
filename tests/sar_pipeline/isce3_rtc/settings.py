# test data storage
PERSISTENT_S3_PROJECT_FOLDER = (
    f"persistent/repositories/sar-pipeline/tests/sar_pipeline/isce3_rtc/results"
)
TEST_S3_BUCKET = "deant-data-public-dev"

# single pol test scene
TEST_1_SCENE = "S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD"
TEST_1_BURST = "t070_149815_iw3"
TEST_1_POLS = ["HH"]
TEST_1_BURST_ST = "2022-01-01T12:47:52.134049Z"
TEST_1_S3_RTC_S1_PRODUCT_SUBPATH = (
    f"ga_s1_nrb_iw_hh_1/{TEST_1_BURST}/2022/01/01/20220101T124752"
)
TEST_1_S3_RTC_S1_STATIC_PRODUCT_SUBPATH = f"ga_s1_nrb_iw_static_1/{TEST_1_BURST}"

# dual pol test scene
TEST_2_SCENE = "S1A_IW_SLC__1SDV_20201129T192619_20201129T192647_035467_042557_D8B8"
TEST_2_BURST = "t045_095837_iw1"
TEST_2_POLS = ["VV", "VH"]
TEST_2_BURST_ST = "2020-11-29T19:26:19.993176Z"
TEST_2_S3_RTC_S1_PRODUCT_SUBPATH = (
    f"ga_s1_nrb_iw_vv_vh_1/{TEST_2_BURST}/2020/11/29/20201129T192619/"
)
TEST_2_S3_RTC_S1_STATIC_PRODUCT_SUBPATH = f"ga_s1_nrb_iw_static_1/{TEST_2_BURST}"

# Set this to true to update the above products in the AWS S3 folder
# See docs in test_full_docker_build_and_run.py for more information
UPDATE_PERSISTENT_TEST_DATA = False
