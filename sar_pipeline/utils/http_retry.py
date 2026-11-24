import logging
import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# (connect timeout, read timeout) in seconds for catalogue requests
DEFAULT_TIMEOUT = (10, 60)
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class CappedRetry(Retry):
    """A urllib3 Retry that caps the wait requested by a server's
    Retry-After header, so a large value cannot stall a job indefinitely."""

    RETRY_AFTER_MAX = 120.0

    def parse_retry_after(self, retry_after: str) -> float:
        return min(super().parse_retry_after(retry_after), self.RETRY_AFTER_MAX)


def make_retry_session(
    total: int = 5,
    backoff_factor: float = 2,
    status_forcelist: frozenset[int] = RETRY_STATUS_CODES,
) -> requests.Session:
    """Make a requests Session that retries GET requests on connection errors,
    read errors and throttling / server error responses, with exponential
    backoff and respect for Retry-After headers (capped).

    Parameters
    ----------
    total : int, optional
        Total number of retries, by default 5
    backoff_factor : float, optional
        Exponential backoff factor in seconds, by default 2
    status_forcelist : frozenset[int], optional
        HTTP status codes to retry, by default 429, 500, 502, 503, 504

    Returns
    -------
    requests.Session
        Session with the retry adapter mounted for http and https.
    """
    retry = CappedRetry(
        total=total,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# requests.Session is not guaranteed to be thread safe and some queries are
# made from a thread pool, so keep one default session per thread.
_thread_local = threading.local()


def _get_default_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = make_retry_session()
        _thread_local.session = session
    return session


def cdse_get(
    url: str,
    *,
    timeout: float | tuple[float, float] = DEFAULT_TIMEOUT,
    session: requests.Session | None = None,
) -> requests.Response:
    """GET a catalogue url with a timeout and retries for throttling and
    transient errors. Raises once the retries are exhausted.

    Parameters
    ----------
    url : str
        The url to request
    timeout : float | tuple[float, float], optional
        Timeout in seconds, or (connect, read) timeouts, by default (10, 60)
    session : requests.Session | None, optional
        Session to use, by default a retrying session from `make_retry_session`

    Returns
    -------
    requests.Response
        The successful response

    Raises
    ------
    requests.HTTPError
        If the final response is an error status
    requests.RequestException
        If the request could not be completed (e.g. connection error, timeout)
    """
    session = session or _get_default_session()
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response
