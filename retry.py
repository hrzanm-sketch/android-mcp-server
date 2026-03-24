"""Simple retry decorator with exponential backoff for transient ADB failures."""

import functools
import logging
import time

logger = logging.getLogger(__name__)


def retry(max_attempts: int = 3, base_delay: float = 1.0, exceptions: tuple = (Exception,)):
    """Retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts (including first try)
        base_delay: Base delay in seconds (doubles each retry)
        exceptions: Tuple of exception types to catch and retry
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            "Attempt %d/%d for %s failed: %s. Retrying in %.1fs...",
                            attempt, max_attempts, func.__name__, e, delay,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "All %d attempts for %s failed. Last error: %s",
                            max_attempts, func.__name__, e,
                        )
            raise last_exception
        return wrapper
    return decorator
