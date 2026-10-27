"""Data cleaning and validation for UK wind actuals (FUELHH) and forecasts (WINDFOR).

All timestamps are normalized to timezone-aware UTC datetimes.
Data types are strictly enforced to prevent downstream computation bugs.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def find_missing_30min_slots(
    series_times: pd.Series,
    expected_start: pd.Timestamp | None = None,
    expected_end: pd.Timestamp | None = None,
) -> pd.DatetimeIndex:
    """Identify missing half-hour (30-minute) UTC slots within a given time range."""
    if series_times.empty:
        return pd.DatetimeIndex([], tz="UTC")

    utc_times = pd.to_datetime(series_times, utc=True)
    start = expected_start if expected_start is not None else utc_times.min()
    end = expected_end if expected_end is not None else utc_times.max()

    expected_range = pd.date_range(start=start, end=end, freq="30min", tz="UTC")
    actual_slots = pd.DatetimeIndex(utc_times.unique())
    missing_slots = expected_range.difference(actual_slots)
    return missing_slots


def clean_fuelhh(
    records: list[dict[str, Any]] | pd.DataFrame,
    expected_start: pd.Timestamp | None = None,
    expected_end: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean actual wind generation records from FUELHH stream.

    Returns:
        (df_cleaned, df_missing_slots):
            df_cleaned: Columns [start_time, generation_mw, settlement_date, settlement_period]
            df_missing_slots: DataFrame listing any missing half-hour timestamps
    """
    if isinstance(records, list):
        if not records:
            empty_df = pd.DataFrame(
                columns=["start_time", "generation_mw", "settlement_date", "settlement_period"]
            )
            return empty_df, pd.DataFrame(columns=["missing_start_time"])
        df = pd.DataFrame(records)
    else:
        df = records.copy()

    # 1. Standardize and parse timestamps to UTC
    if "startTime" not in df.columns:
        raise ValueError("Missing required column 'startTime' in FUELHH records")
    df["start_time"] = pd.to_datetime(df["startTime"], utc=True)

    # 2. Enforce numeric generation values (MW)
    if "generation" not in df.columns:
        raise ValueError("Missing required column 'generation' in FUELHH records")
    df["generation_mw"] = pd.to_numeric(df["generation"], errors="coerce")

    # Flag and log any records with unparseable generation
    invalid_gen = df["generation_mw"].isna()
    if invalid_gen.any():
        logger.warning("Dropping %d FUELHH records with invalid/null generation values", invalid_gen.sum())
        df = df[~invalid_gen]

    # Clean optional metadata columns
    if "settlementDate" in df.columns:
        df["settlement_date"] = df["settlementDate"].astype(str)
    else:
        df["settlement_date"] = df["start_time"].dt.strftime("%Y-%m-%d")

    if "settlementPeriod" in df.columns:
        df["settlement_period"] = pd.to_numeric(df["settlementPeriod"], errors="coerce").fillna(0).astype(int)
    else:
        df["settlement_period"] = 0

    # 3. Deduplicate on start_time (keep latest publication if publishTime is available, else keep last)
    initial_len = len(df)
    if "publishTime" in df.columns:
        df["publish_time"] = pd.to_datetime(df["publishTime"], utc=True)
        df = df.sort_values(by=["start_time", "publish_time"]).drop_duplicates(subset=["start_time"], keep="last")
    else:
        df = df.drop_duplicates(subset=["start_time"], keep="last")

    duplicates_removed = initial_len - len(df)
    if duplicates_removed > 0:
        logger.info("Deduplicated FUELHH records: removed %d duplicate start_time rows", duplicates_removed)

    # 4. Sort chronologically
    df = df.sort_values(by="start_time").reset_index(drop=True)

    # 5. Check for missing half-hour slots
    missing = find_missing_30min_slots(df["start_time"], expected_start=expected_start, expected_end=expected_end)
    df_missing = pd.DataFrame({"missing_start_time": missing})
    if len(missing) > 0:
        logger.warning("Detected %d missing 30-min settlement intervals in FUELHH data", len(missing))

    # Keep only the target clean schema
    output_cols = ["start_time", "generation_mw", "settlement_date", "settlement_period"]
    return df[output_cols].copy(), df_missing


def clean_windfor(
    records: list[dict[str, Any]] | pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Clean wind generation forecast records from WINDFOR stream.

    Returns:
        (df_cleaned, quality_report):
            df_cleaned: Columns [start_time, publish_time, generation_mw, horizon_hours]
            quality_report: Summary dictionary with count of duplicates, negative MW, anomalies
    """
    if isinstance(records, list):
        if not records:
            empty_df = pd.DataFrame(
                columns=["start_time", "publish_time", "generation_mw", "horizon_hours"]
            )
            return empty_df, {"total": 0, "duplicates": 0, "negative_gen": 0, "negative_horizon": 0}
        df = pd.DataFrame(records)
    else:
        df = records.copy()

    # 1. Validate required columns
    for col in ("startTime", "publishTime", "generation"):
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in WINDFOR records")

    # 2. Parse timestamps to UTC
    df["start_time"] = pd.to_datetime(df["startTime"], utc=True)
    df["publish_time"] = pd.to_datetime(df["publishTime"], utc=True)

    # 3. Enforce numeric generation
    df["generation_mw"] = pd.to_numeric(df["generation"], errors="coerce")
    invalid_gen = df["generation_mw"].isna()
    if invalid_gen.any():
        logger.warning("Dropping %d WINDFOR records with invalid generation values", invalid_gen.sum())
        df = df[~invalid_gen]

    # 4. Deduplicate on (start_time, publish_time)
    initial_len = len(df)
    df = df.drop_duplicates(subset=["start_time", "publish_time"], keep="last")
    duplicates_removed = initial_len - len(df)

    # 5. Calculate forecast horizon (difference between target delivery startTime and publishTime)
    # A positive horizon means forecast was published before delivery; negative means outturn/retrospective
    df["horizon_hours"] = (df["start_time"] - df["publish_time"]).dt.total_seconds() / 3600.0

    # 6. Quality metrics
    negative_gen_count = int((df["generation_mw"] < 0).sum())
    negative_horizon_count = int((df["horizon_hours"] < 0).sum())

    quality_report = {
        "total_records": len(df),
        "duplicates_removed": duplicates_removed,
        "negative_generation_count": negative_gen_count,
        "negative_horizon_count": negative_horizon_count,
    }

    if negative_gen_count > 0:
        logger.warning("Found %d records with negative forecast generation in WINDFOR", negative_gen_count)
    if negative_horizon_count > 0:
        logger.warning(
            "Found %d records published after slot start time in WINDFOR (negative horizon)",
            negative_horizon_count,
        )

    # 7. Sort by target time then publish time for deterministic ordering
    df = df.sort_values(by=["start_time", "publish_time"]).reset_index(drop=True)

    output_cols = ["start_time", "publish_time", "generation_mw", "horizon_hours"]
    return df[output_cols].copy(), quality_report
