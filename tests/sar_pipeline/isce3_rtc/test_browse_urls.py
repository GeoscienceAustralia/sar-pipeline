"""Offline tests for making and parsing product browse urls"""

import pytest

from sar_pipeline.pipelines.isce3_rtc.metadata.odc import (
    make_rtc_s1_product_browse_url,
    make_rtc_s1_static_product_browse_url,
    get_s3_bucket_from_product_browse_url,
    get_s3_prefix_from_product_browse_url,
)

PREFIX = "baseline/ga_s1_nrb_iw_hh_1/t070_149815_iw3/2022/01/01/20220101T124752/"
MAKE_URL_FUNCTIONS = [
    make_rtc_s1_product_browse_url,
    make_rtc_s1_static_product_browse_url,
]


@pytest.mark.parametrize("make_url", MAKE_URL_FUNCTIONS)
@pytest.mark.parametrize(
    "s3_bucket", ["dea-public-data", "dea-public-data-dev", "any-other-bucket"]
)
def test_browse_url_round_trip(make_url, s3_bucket):
    url = make_url(s3_bucket, PREFIX)

    assert url == (
        f"https://{s3_bucket}.s3.ap-southeast-2.amazonaws.com/index.html?prefix={PREFIX}"
    )
    assert get_s3_bucket_from_product_browse_url(url) == s3_bucket
    assert get_s3_prefix_from_product_browse_url(url) == PREFIX


@pytest.mark.parametrize("make_url", MAKE_URL_FUNCTIONS)
def test_browse_url_with_base_url(make_url):
    base_url = "https://example.com/browse/"

    url = make_url("dea-public-data", PREFIX, base_url=base_url)

    assert url == f"{base_url}{PREFIX}"
    assert get_s3_prefix_from_product_browse_url(url, base_url=base_url) == PREFIX


def test_parse_published_data_dev_browse_url():
    url = f"https://data.dev.dea.ga.gov.au/?prefix={PREFIX}"

    assert get_s3_bucket_from_product_browse_url(url) == "dea-public-data-dev"
    assert get_s3_prefix_from_product_browse_url(url) == PREFIX
