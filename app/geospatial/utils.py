"""
JSON serialisation utilities.

GeoPandas and pandas introduce types that are not JSON-serialisable by
default (``numpy.int64``, ``numpy.float64``, ``pandas.NA``, ``datetime``,
etc.). ``json_safe()`` recursively converts these to Python primitives so
that feature properties can be stored in a JSON database column without
errors.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def json_safe(value: Any) -> Any:
    """Recursively convert *value* into a JSON-serialisable Python primitive.

    Handles:
    - ``None`` / ``pd.NA`` / ``np.nan`` / ``np.inf`` → ``None``
    - ``numpy`` scalars → their Python equivalent via ``.item()``
    - ``datetime`` / ``date`` → ISO-8601 string
    - ``dict`` → dict with recursively safe values
    - ``list`` / ``tuple`` / ``set`` → list with recursively safe values
    - Anything else → ``str(value)`` as a fallback

    Parameters
    ----------
    value:
        Any value that may originate from a GeoPandas row.

    Returns
    -------
    Any
        A value that is safe to pass to ``json.dumps()`` or store in a
        SQLAlchemy JSON column.
    """
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        # Catch non-finite floats that JSON cannot represent
        if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
            return None
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, np.generic):
        # Convert numpy scalars (int64, float32, bool_, etc.) to Python types
        return json_safe(value.item())

    if isinstance(value, dict):
        return {str(key): json_safe(val) for key, val in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]

    # pandas NA (different from numpy nan)
    if value is pd.NA:
        return None

    # Catch remaining pandas NA-like values (e.g. pd.NaT, NAType)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    return str(value)
