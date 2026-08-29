"""Shared JSON-safety helpers for the route handlers.

pandas/numpy scalar types (np.float64, np.int64, NaN) aren't natively
JSON-serializable the way FastAPI's default encoder expects. Routing values
through DataFrame/Series.to_json() (pandas' own encoder) sidesteps that
instead of hand-rolling numpy-type coercion per field.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import pandas as pd


def frame_to_records(frame: Optional[pd.DataFrame]) -> list[dict]:
    if frame is None or frame.empty:
        return []
    return json.loads(frame.to_json(orient="records"))


def series_to_dict(row: Any) -> dict:
    if row is None:
        return {}
    if isinstance(row, pd.Series):
        return json.loads(row.to_json())
    return dict(row)


def default_user_id(explicit: Optional[int]) -> int:
    """Single-user tool for now — see MEDALLION_DEFAULT_USER_ID in .env.example."""
    if explicit is not None:
        return int(explicit)
    return int(os.environ.get("MEDALLION_DEFAULT_USER_ID", "1"))
