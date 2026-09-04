from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from requests.exceptions import RequestException, ConnectionError, Timeout
from app.utils.logger import logger
import logging

def nse_retry(fn):
    """
    Tenacity retry decorator for nselib calls.
    Lazily fetches retry parameters from app.config to prevent circular import issues.
    """
    def wrapper(*args, **kwargs):
        try:
            from app.config import config
            max_attempts = config.NSE_MAX_RETRIES
            min_wait = config.NSE_RETRY_MIN_WAIT
            max_wait = config.NSE_RETRY_MAX_WAIT
        except Exception:
            max_attempts, min_wait, max_wait = 3, 2, 10

        retry_decorator = retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(min=min_wait, max=max_wait),
            retry=retry_if_exception_type((RequestException, ConnectionError, Timeout, Exception)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True
        )
        return retry_decorator(fn)(*args, **kwargs)
    return wrapper
