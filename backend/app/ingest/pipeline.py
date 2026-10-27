"""End-to-end ingest pipeline coordinating fetch, clean, and store operations.

Pulls Elexon BMRS FUELHH (WIND) and WINDFOR data relevant to January 2026
energy purchase decisions (including late Dec 2025 and early Feb 2026 buffers).
All processing occurs strictly in UTC.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.ingest.cleaner import clean_fuelhh, clean_windfor
from backend.app.ingest.client import ElexonClient
from backend.app.ingest.storage import DEFAULT_DB_PATH, save_actuals, save_forecasts

logger = logging.getLogger(__name__)


def run_ingest(
    start_date: date = date(2025, 12, 30),
    end_date: date = date(2026, 2, 3),
    forecast_publish_from: datetime = datetime(2025, 12, 25, 0, 0, 0, tzinfo=timezone.utc),
    forecast_publish_to: datetime = datetime(2026, 2, 3, 23, 59, 59, tzinfo=timezone.utc),
    db_path: Path | str = DEFAULT_DB_PATH,
    chunk_days: int = 7,
) -> dict[str, Any]:
    """Execute complete ingestion pipeline for both actuals and forecasts."""
    client = ElexonClient()
    summary: dict[str, Any] = {}

    # --- 1. ACTUALS INGESTION (FUELHH - WIND) ---
    logger.info("=== Starting FUELHH (WIND) Ingest ===")
    raw_actuals = client.fetch_fuelhh_wind(start_date=start_date, end_date=end_date, chunk_days=chunk_days)
    df_actuals, df_missing_slots = clean_fuelhh(raw_actuals)
    saved_actuals_count = save_actuals(df_actuals, db_path=db_path)

    summary["actuals"] = {
        "raw_count": len(raw_actuals),
        "cleaned_count": len(df_actuals),
        "saved_count": saved_actuals_count,
        "missing_30min_slots_count": len(df_missing_slots),
        "min_time": df_actuals["start_time"].min().isoformat() if not df_actuals.empty else None,
        "max_time": df_actuals["start_time"].max().isoformat() if not df_actuals.empty else None,
    }

    # --- 2. FORECASTS INGESTION (WINDFOR) ---
    logger.info("=== Starting WINDFOR Ingest ===")
    raw_forecasts = client.fetch_windfor(
        publish_from=forecast_publish_from,
        publish_to=forecast_publish_to,
        chunk_days=chunk_days,
    )
    df_forecasts, forecast_quality = clean_windfor(raw_forecasts)
    saved_forecasts_count = save_forecasts(df_forecasts, db_path=db_path)

    summary["forecasts"] = {
        "raw_count": len(raw_forecasts),
        "cleaned_count": len(df_forecasts),
        "saved_count": saved_forecasts_count,
        "quality_report": forecast_quality,
        "unique_start_times": int(df_forecasts["start_time"].nunique()) if not df_forecasts.empty else 0,
        "min_publish_time": df_forecasts["publish_time"].min().isoformat() if not df_forecasts.empty else None,
        "max_publish_time": df_forecasts["publish_time"].max().isoformat() if not df_forecasts.empty else None,
        "min_start_time": df_forecasts["start_time"].min().isoformat() if not df_forecasts.empty else None,
        "max_start_time": df_forecasts["start_time"].max().isoformat() if not df_forecasts.empty else None,
    }

    logger.info("=== Ingest Completed Successfully ===")
    return summary
