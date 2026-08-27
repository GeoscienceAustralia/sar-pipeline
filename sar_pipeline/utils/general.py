import time
import logging
from functools import wraps
from datetime import datetime
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def log_timing(func):
    """
    Decorator that logs the execution time of a function.

    Parameters
    ----------
    func : callable
        The function whose execution time is to be measured and logged.

    Returns
    -------
    callable
        A wrapper function that executes the original function and logs the elapsed time in seconds.

    Notes
    -----
    This decorator uses the `logging` module to log the execution time at the INFO level.
    The log message format is: "timing : <function_name> : <elapsed_time>s".

    Examples
    --------
    @log_timing
    def slow_function():
        time.sleep(2)
    > slow_function()
    > timing : slow_function : 2.00s
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"timing : {func.__name__} : {elapsed:.2f}s")
        return result

    return wrapper


def format_dt_utc(dt: datetime) -> str:
    """Formats a datetime as an ISO-8601 UTC string with milliseconds precision.

    Example:
        2025-01-28T20:56:38.451412Z -> 2025-01-28T20:56:38.451Z
    """
    s = dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return re.sub(r"(\.\d{3})\d{3}Z$", r"\1Z", s)
