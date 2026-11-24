import datetime
import socket
from unittest import mock

import pystac
import pystac.validation
from pystac.validation.stac_validator import JsonSchemaSTACValidator
import pytest

from sar_pipeline.pipelines.isce3_rtc.metadata.stac import (
    RTC_S1_STAC_EXTENSIONS,
    STAC_EXTENSIONS,
)
from sar_pipeline.utils.stac_schemas import (
    load_local_stac_schemas,
    use_local_stac_schemas,
)


def _network_blocked(*args, **kwargs):
    raise OSError("network access is blocked in this test")


@pytest.fixture
def no_network():
    with (
        mock.patch("urllib.request.urlopen", side_effect=_network_blocked),
        mock.patch.object(socket.socket, "connect", side_effect=_network_blocked),
    ):
        yield


@pytest.fixture
def local_validator():
    validator = use_local_stac_schemas()
    yield validator
    # restore a default validator so other tests are unaffected
    pystac.validation.set_validator(JsonSchemaSTACValidator())


def _make_item(stac_extensions: list[str]) -> pystac.Item:
    """A minimal burst-like item that satisfies all the declared extensions."""
    properties = {
        "sar:frequency_band": "C",
        "sar:instrument_mode": "IW",
        "sar:polarizations": ["VV", "VH"],
        "sat:orbit_state": "descending",
        "sat:relative_orbit": 70,
        "s1:orbit_source": "POEORB",
        "processing:level": "L2",
        "processing:software": {"isce3": "0.15.0"},
        "storage:schemes": {
            "aws": {
                "type": "aws-s3",
                "platform": "https://{bucket}.s3.{region}.amazonaws.com",
                "bucket": "dea-public-data-dev",
                "region": "ap-southeast-2",
            }
        },
        "ceosard:type": "radar",
        "ceosard:specification": "NRB",
        "ceosard:specification_version": "5.5",
        "proj:code": "EPSG:32755",
        "product:type": "RTC_S1",
    }
    item = pystac.Item(
        id="ga_s1a_nrb_iw_1-0-0_t070-149815-iw2_20220101t124745",
        geometry={
            "type": "Polygon",
            "coordinates": [
                [[150, -70], [151, -70], [151, -69], [150, -69], [150, -70]]
            ],
        },
        bbox=[150, -70, 151, -69],
        datetime=datetime.datetime(
            2022, 1, 1, 12, 47, 45, tzinfo=datetime.timezone.utc
        ),
        properties=properties,
        stac_extensions=stac_extensions,
    )
    item.add_link(
        pystac.Link(
            rel="ceos-ard-specification",
            target="https://ceos.org/ard/files/PFS/NRB/v5.5/CARD4L-PFS_NRB_v5.5.pdf",
            media_type=pystac.MediaType.PDF,
        )
    )
    item.add_asset(
        "VV",
        pystac.Asset(
            href="ga_s1a_nrb_iw_1-0-0_t070-149815-iw2_20220101t124745_VV-gamma0.tif",
            media_type=pystac.MediaType.COG,
            roles=["data"],
            extra_fields={"raster:spatial_resolution": 20},
        ),
    )
    return item


def test_all_declared_schemas_are_vendored():
    schemas = load_local_stac_schemas()
    for uri in STAC_EXTENSIONS + RTC_S1_STAC_EXTENSIONS:
        assert uri in schemas


@pytest.mark.parametrize(
    "stac_extensions",
    [STAC_EXTENSIONS, STAC_EXTENSIONS + RTC_S1_STAC_EXTENSIONS],
    ids=["RTC_S1_STATIC", "RTC_S1"],
)
def test_validate_item_without_network(local_validator, no_network, stac_extensions):
    item = _make_item(stac_extensions)
    validated = item.validate()
    # the core item schema plus every extension schema
    assert len(validated) == len(stac_extensions) + 1


def test_invalid_item_still_fails_without_network(local_validator, no_network):
    item = _make_item(STAC_EXTENSIONS + RTC_S1_STAC_EXTENSIONS)
    item.properties["sar:frequency_band"] = "not-a-band"
    with pytest.raises(pystac.errors.STACValidationError):
        item.validate()


def test_default_validator_needs_network(no_network):
    # without the local schemas the extension schemas are fetched remotely,
    # which confirms the network block in these tests is effective
    pystac.validation.set_validator(JsonSchemaSTACValidator())
    item = _make_item(STAC_EXTENSIONS)
    with pytest.raises(Exception, match="network access is blocked"):
        item.validate()
