"""
Overview:
This file can be used to test the changes (if any) to the outputs of the
isce3-rtc sar pipeline. A folder is generated at the project root which
contains a report showing the changes in metadata and products to existing
product outputs. Existing products for comparison are stored in AWS at the paths
specified by the `RTC_S1_PRODUCT_S3_PATH` and `RTC_S1_STATIC_PRODUCT_S3_PATH`
below. If changes occur, an updated version of the products should be uploaded
to AWS and the associated paths should be changed. This ensures moving forward
changes to code and the associated impact on metadata and data quality can be
properly tracked.

Steps:
1.  Download the RTC_S1 and RTC_S1 products for the comparison
2.  Build a docker image for the current code state
3.  Run the pipeline for RTC_S1_STATIC, upload to a temporary location
    and store the outputs locally.
4.  Run the pipeline for RTC_S1 with linking to the above RTC_S1_STATIC products,
    upload to a temporary location and store the outputs locally.
5.  Run comparison scripts to determine the difference in the products
6.  OPTIONAL, if changes occur and a new release is planned. The updated products
    Should be uploaded to AWS and referenced in this file for future data quality
    assessments.

"""

import pytest
import json
from sar_pipeline.aws.compare.metadata import compare_json


def test_compare_json():
    json1 = "/data/metadata_1.json"
    json2 = "/data/metadata_2.json"
    differences = compare_json(json1, json2)

    with open("/data/json_differences.json", "w") as out_file:
        json.dump(differences, out_file, indent=2)

    print(f"Found {len(differences)} differences. Saved to json_differences.json")
