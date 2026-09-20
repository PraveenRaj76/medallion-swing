"""Shared retry-with-backoff helper for the live-data provider layer.

Root-cause context (2026-09-11 data-authenticity review): every HTTP/scrape
call in this package (Screener.in via curl_cffi, Yahoo Finance via yfinance,
SEC EDGAR via requests, NSE/BSE via curl_cffi) made exactly ONE attempt —
a single transient blip (a momentary timeout, a rate-limit 429, a dropped
connection) permanently gave up for that refresh cycle instead of trying
again, silently leaving that ticker on its last successfully-fetched value
with no indication a fresher value was ever attempted and failed. This
module is the one retry policy every provider now shares, so "how many
times do we try" and "what counts as worth retrying" isn't reimplemented
(and isn't allowed to quietly drift) per call site.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, Optional, TypeVar

logger = logging.getLogger("medallion.providers")

T = TypeVar("T")

# HTTP status codes worth retrying — transient / server-side. Deliberately
# excludes 400/401/403/404: those mean the source is correctly telling us
# no, and retrying just wastes time and hammers a source that already
# answered.
RETRIABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.6,
    label: str = "request",
) -> Optional[T]:
    """Call fn() up to `attempts` times with jittered exponential backoff.

    fn decides what's worth retrying by RAISING (any exception here is
    treated as transient and retried) vs. returning None/a value (fn has
    already decided the failure is final — e.g. a non-retriable 4xx — and
    retry_call will not react to that). On final failure this returns None
    rather than raising, matching what every existing caller in this
    codebase already does with a failed fetch: treat it as "this source
    didn't answer" and degrade gracefully (skip the checklist item, fall
    back to a secondary source, or keep the prior DB value).
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
            last_exc = exc
            if attempt < attempts:
                delay = base_delay * (2 ** (attempt - 1)) * (1 + random.random() * 0.3)
                logger.info(
                    "%s attempt %d/%d failed (%s) - retrying in %.1fs",
                    label, attempt, attempts, exc, delay,
                )
                time.sleep(delay)
    logger.warning("%s failed after %d attempt(s): %s", label, attempts, last_exc)
    return None
