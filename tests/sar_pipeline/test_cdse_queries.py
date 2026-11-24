"""Offline tests for bounded / retried CDSE catalogue requests and the
scene metadata fallback to the ASF. A local http server stands in for the CDSE."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import pytest
import requests

from sar_pipeline.pipelines.isce3_rtc.utils import burst_utils
from sar_pipeline.pipelines.isce3_rtc.utils.burst_utils import (
    get_burst_info_for_scene_from_cdse,
)
from sar_pipeline.utils import http_retry
from sar_pipeline.utils.http_retry import CappedRetry, cdse_get, make_retry_session

SCENE = "S1A_IW_SLC__1SDV_20220101T124744_20220101T124814_041267_04E7A2_1DAD"

FOOTPRINT = {
    "type": "Polygon",
    "coordinates": [[[130, -20], [131, -20], [131, -21], [130, -21], [130, -20]]],
}


def _burst(burst_id, swath, pol):
    return {
        "RelativeOrbitNumber": 70,
        "BurstId": burst_id,
        "SwathIdentifier": swath,
        "BeginningDateTime": "2022-01-01T12:47:44.000000Z",
        "EndingDateTime": "2022-01-01T12:47:47.000000Z",
        "AzimuthTime": "2022-01-01T12:47:45.123456Z",
        "GeoFootprint": FOOTPRINT,
        "PolarisationChannels": pol,
    }


ODATA_RESPONSE = {
    "value": [
        _burst(149815, "IW2", "VV"),
        _burst(149815, "IW2", "VH"),
        _burst(149816, "IW3", "VV"),
    ]
}


class _FakeCdse:
    """Local http server that replays a list of (status, delay_seconds) responses.
    The last entry is repeated once the list is exhausted."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                fake.requests.append(self.path)
                idx = min(len(fake.requests), len(fake.responses)) - 1
                status, delay = fake.responses[idx]
                if delay:
                    time.sleep(delay)
                body = json.dumps(ODATA_RESPONSE if status == 200 else {}).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/odata/v1/Bursts"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def no_backoff_session(monkeypatch):
    """Use a retrying session without backoff sleeps for the default session."""
    session = make_retry_session(total=5, backoff_factor=0)
    monkeypatch.setattr(http_retry, "_get_default_session", lambda: session)
    return session


def test_burst_query_retries_after_throttling(no_backoff_session):
    with _FakeCdse([(429, 0), (200, 0)]) as cdse:
        burst_info = get_burst_info_for_scene_from_cdse(SCENE, base_url=cdse.url)

    assert len(cdse.requests) == 2
    assert SCENE in requests.utils.unquote(cdse.requests[-1])
    assert set(burst_info.keys()) == {"t070_149815_iw2", "t070_149816_iw3"}
    assert burst_info["t070_149815_iw2"]["pols"] == ["VV", "VH"]
    assert burst_info["t070_149816_iw3"]["pols"] == ["VV"]
    assert burst_info["t070_149815_iw2"]["azimuth_time"].microsecond == 123456


def test_burst_query_raises_after_persistent_server_errors(no_backoff_session):
    with _FakeCdse([(503, 0)]) as cdse:
        with pytest.raises(requests.HTTPError):
            get_burst_info_for_scene_from_cdse(SCENE, base_url=cdse.url)

    # one initial request plus 5 retries
    assert len(cdse.requests) == 6


def test_cdse_get_times_out_promptly():
    session = make_retry_session(total=1, backoff_factor=0)
    with _FakeCdse([(200, 3)]) as cdse:
        t0 = time.monotonic()
        with pytest.raises((requests.Timeout, requests.ConnectionError)):
            cdse_get(cdse.url, timeout=0.2, session=session)
        elapsed = time.monotonic() - t0

    # two attempts of 0.2s each, far below the 3s the server takes
    assert elapsed < 2


def test_chunk_query_uses_bounded_request(no_backoff_session):
    with _FakeCdse([(500, 0), (200, 0)]) as cdse:
        results = burst_utils._make_chunk_cdse_request(
            base_url=cdse.url,
            chunk_start=burst_utils.datetime(2022, 1, 1, 12, 0),
            chunk_end=burst_utils.datetime(2022, 1, 1, 12, 5),
            product_type="IW_SLC__1S",
            geometry=burst_utils.shapely.geometry.shape(FOOTPRINT),
        )

    assert len(cdse.requests) == 2
    assert len(results) == 3


def test_retry_after_is_capped():
    retry = CappedRetry(total=1)
    assert retry.parse_retry_after("5") == 5
    assert retry.parse_retry_after("100000") == CappedRetry.RETRY_AFTER_MAX


class _LazyFailingQuery:
    """Mimics a cdsetool FeatureQuery whose request fails when results are accessed."""

    def __len__(self):
        raise ValueError("__len__() should return >= 0")

    def __iter__(self):
        raise ValueError("__len__() should return >= 0")

    def __getitem__(self, index):
        raise ValueError("__len__() should return >= 0")


@pytest.mark.parametrize(
    "cdse_result",
    [_LazyFailingQuery(), [], iter([])],
    ids=["lazy_fail", "empty", "empty_iter"],
)
def test_scene_metadata_falls_back_to_asf(cdse_result):
    from sar_pipeline.pipelines.isce3_rtc import cli

    asf_results = [mock.sentinel.asf_scene]
    with (
        mock.patch.object(cli, "query_scene_from_cdse", return_value=cdse_result),
        mock.patch.object(
            cli, "query_scene_from_asf", return_value=asf_results
        ) as mock_asf,
    ):
        scene_results, metadata_src = cli._query_scene_metadata(SCENE)

    mock_asf.assert_called_once_with(SCENE)
    assert metadata_src == "ASF"
    assert scene_results is asf_results


def test_scene_metadata_uses_cdse_when_available():
    from sar_pipeline.pipelines.isce3_rtc import cli

    cdse_scene = {"Name": f"{SCENE}.SAFE", "GeoFootprint": FOOTPRINT}
    with (
        mock.patch.object(
            cli, "query_scene_from_cdse", return_value=iter([cdse_scene])
        ),
        mock.patch.object(cli, "query_scene_from_asf") as mock_asf,
    ):
        scene_results, metadata_src = cli._query_scene_metadata(SCENE)

    mock_asf.assert_not_called()
    assert metadata_src == "CDSE"
    assert scene_results == [cdse_scene]
    assert scene_results[0]["GeoFootprint"] == FOOTPRINT


def test_scene_metadata_falls_back_when_real_feature_query_fails():
    """Use cdsetool's real (lazy) FeatureQuery with the fetch simulating
    exhausted retries. Accessing len() raises ValueError as total_results
    stays -1. This must fall back to the ASF rather than escape."""
    from cdsetool.query import FeatureQuery

    from sar_pipeline.pipelines.isce3_rtc import cli

    def exhausted_fetch(self):
        self.next_url = None  # cdsetool's behaviour after 10 failed attempts

    asf_results = [mock.sentinel.asf_scene]
    with (
        mock.patch.object(
            FeatureQuery, "_FeatureQuery__fetch_features", exhausted_fetch
        ),
        mock.patch.object(
            cli, "query_scene_from_asf", return_value=asf_results
        ) as mock_asf,
    ):
        with pytest.raises(ValueError):
            len(cli.query_scene_from_cdse(SCENE))
        scene_results, metadata_src = cli._query_scene_metadata(SCENE)

    mock_asf.assert_called_once_with(SCENE)
    assert metadata_src == "ASF"
