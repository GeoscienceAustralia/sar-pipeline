from sar_pipeline.pipelines.isce3_rtc.metadata.xml import XMLMapper
from sar_pipeline.utils.aws import S3Util
from shapely.geometry import shape
import json
import pytest
import shapely

from settings import (
    TEST_S3_BUCKET,
    TEST_1_BENCHMARK_RTC_S1_S3_PRODUCT_FOLDER,
    TEST_1_POLS,
    TEST_3_BENCHMARK_RTC_S1_S3_PRODUCT_FOLDER,
    TEST_3_POLS,
    TEST_4_BENCHMARK_RTC_S1_S3_PRODUCT_FOLDER,
    TEST_4_POLS,
)

EXTENT_TAG = "CEOS-ARDProductAttributes/ProductGeographicalExtent"


@pytest.mark.parametrize(
    "s3_product_folder, polarisations",
    [
        (TEST_1_BENCHMARK_RTC_S1_S3_PRODUCT_FOLDER, TEST_1_POLS),
        # antimeridian over water
        (TEST_3_BENCHMARK_RTC_S1_S3_PRODUCT_FOLDER, TEST_3_POLS),
        # antimeridian over land
        (TEST_4_BENCHMARK_RTC_S1_S3_PRODUCT_FOLDER, TEST_4_POLS),
    ],
)
def test_xml_extent_covers_burst_footprint(tmp_path, s3_product_folder, polarisations):
    """The XML extent holds the burst's STAC footprint, and only a little more:
    across the antimeridian it's split at 180°, not boxed the other way round the globe.
    """
    stac_path = _download_benchmark_file(s3_product_folder, "_stac-item.json", tmp_path)
    h5_path = _download_benchmark_file(s3_product_folder, "_metadata.h5", tmp_path)

    xml = XMLMapper(
        stac_path=stac_path,
        h5_path=h5_path,
        polarisations=polarisations,
        backscatter_convention="gamma0",
    )
    xml.populate_xml()
    xml.populate_special_xml_mappings()

    extent = shapely.from_wkt(xml.xml.getroot().find(".//" + EXTENT_TAG).text)
    footprint = shape(json.loads(stac_path.read_text())["geometry"])
    assert extent.covers(footprint)
    # a box the other way round the globe is hundreds of times the footprint
    assert extent.area < 10 * footprint.area


def _download_benchmark_file(s3_product_folder, suffix, local_dir):
    s3 = S3Util(unsigned=True).s3
    objects = s3.list_objects_v2(Bucket=TEST_S3_BUCKET, Prefix=s3_product_folder)
    key = next(o["Key"] for o in objects["Contents"] if o["Key"].endswith(suffix))
    local_path = local_dir / key.split("/")[-1]
    s3.download_file(TEST_S3_BUCKET, key, str(local_path))
    return local_path
