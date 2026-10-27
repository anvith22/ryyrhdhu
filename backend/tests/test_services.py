"""Unit tests for forecast evaluation services using synthetic SQLite fixtures at hourly resolution."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from backend.app.ingest.storage import init_db
from backend.app.services.forecast_service import (
    compare,
    error_distribution,
    metrics,
    metrics_by_cutoff,
    metrics_by_horizon,
    metrics_daily,
    select_latest_forecasts,
)


@pytest.fixture
def synthetic_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database populated with controlled synthetic test records."""
    db_path = tmp_path / "test_wind.db"
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    with conn:
        # Delivery date under test: 2026-01-05
        # Cutoff (D-1 at 09:00 UTC) = 2026-01-04 09:00:00Z

        # 1. Actuals: half-hourly pairs to test hourly averaging
        # Hour 10:00: 950 + 1050 -> mean = 1000.0 MW
        # Hour 11:00: 1900 + 2100 -> mean = 2000.0 MW
        # Hour 12:00: 1400 + 1600 -> mean = 1500.0 MW
        # Hour 13:00: 1800 + 1800 -> mean = 1800.0 MW
        actual_rows = [
            ("2026-01-05T10:00:00Z", 950.0, "2026-01-05", 21),
            ("2026-01-05T10:30:00Z", 1050.0, "2026-01-05", 22),
            ("2026-01-05T11:00:00Z", 1900.0, "2026-01-05", 23),
            ("2026-01-05T11:30:00Z", 2100.0, "2026-01-05", 24),
            ("2026-01-05T12:00:00Z", 1400.0, "2026-01-05", 25),
            ("2026-01-05T12:30:00Z", 1600.0, "2026-01-05", 26),
            ("2026-01-05T13:00:00Z", 1800.0, "2026-01-05", 27),
            ("2026-01-05T13:30:00Z", 1800.0, "2026-01-05", 28),
        ]
        conn.executemany(
            "INSERT INTO actuals_wind (start_time, generation_mw, settlement_date, settlement_period) VALUES (?, ?, ?, ?);",
            actual_rows,
        )

        # 2. Hourly Forecasts
        # Hour 10:00:
        # - Early forecast at 04:00 (before cutoff) -> gen = 1100
        # - Latest forecast before cutoff at 08:30 -> gen = 1200 (error = 1200 - 1000 = +200)
        # - Future forecast at 09:30 (AFTER cutoff) -> gen = 1350 (MUST BE IGNORED)
        # Hour 11:00:
        # - Published at 08:00 (before cutoff) -> gen = 1700 (error = 1700 - 2000 = -300)
        # Hour 12:00:
        # - Published at 07:30 (before cutoff) -> gen = 1600 (error = 1600 - 1500 = +100)
        # Hour 13:00:
        # - No forecast published before cutoff! Only published at 10:00 (after cutoff)
        # Retrospective record (for horizon test):
        # - publish_time > start_time -> horizon = -2.0
        forecast_rows = [
            # Hour 10:00 publications
            ("2026-01-05T10:00:00Z", "2026-01-04T04:00:00Z", 1100.0, 30.0),
            ("2026-01-05T10:00:00Z", "2026-01-04T08:30:00Z", 1200.0, 25.5),  # ELIGIBLE LATEST
            ("2026-01-05T10:00:00Z", "2026-01-04T09:30:00Z", 1350.0, 24.5),  # INELIGIBLE (after cutoff)
            # Hour 11:00 publications
            ("2026-01-05T11:00:00Z", "2026-01-04T08:00:00Z", 1700.0, 27.0),  # ELIGIBLE LATEST
            # Hour 12:00 publications
            ("2026-01-05T12:00:00Z", "2026-01-04T07:30:00Z", 1600.0, 28.5),  # ELIGIBLE LATEST
            # Hour 13:00 (only published after cutoff)
            ("2026-01-05T13:00:00Z", "2026-01-04T10:00:00Z", 1850.0, 27.0),  # INELIGIBLE
            # Retrospective negative-horizon record
            ("2026-01-05T06:00:00Z", "2026-01-05T08:00:00Z", 950.0, -2.0),
        ]
        conn.executemany(
            "INSERT INTO forecasts_wind (start_time, publish_time, generation_mw, horizon_hours) VALUES (?, ?, ?, ?);",
            forecast_rows,
        )

    conn.close()
    return db_path


def test_cutoff_selection_picks_latest_before_cutoff_and_ignores_later(synthetic_db: Path):
    """(a) Test that cutoff selection picks latest publishTime <= cutoff and strictly ignores later publications."""
    delivery_date = date(2026, 1, 5)
    cutoff_hour = 9

    selected = select_latest_forecasts(delivery_date, cutoff_hour_utc=cutoff_hour, db_path=synthetic_db)
    slot_map = {s["start_time"]: s for s in selected}

    slot_10 = slot_map["2026-01-05T10:00:00Z"]
    assert slot_10["generation_mw"] == 1200.0
    assert slot_10["publish_time"] == "2026-01-04T08:30:00Z"
    assert slot_10["horizon_hours"] == 25.5


def test_unforecasted_slot_is_null_and_excluded_from_metrics(synthetic_db: Path):
    """(b) Test that a slot with no eligible forecast is reported unforecasted (null) and excluded from metrics."""
    delivery_date = date(2026, 1, 5)
    cutoff_hour = 9

    selected = select_latest_forecasts(delivery_date, cutoff_hour_utc=cutoff_hour, db_path=synthetic_db)
    slot_map = {s["start_time"]: s for s in selected}

    slot_13 = slot_map["2026-01-05T13:00:00Z"]
    assert slot_13["generation_mw"] is None
    assert slot_13["publish_time"] is None

    comp = compare(delivery_date, cutoff_hour_utc=cutoff_hour, db_path=synthetic_db)
    assert len(comp["slots"]) == 24
    c_map = {s["start_time"]: s for s in comp["slots"]}
    assert c_map["2026-01-05T13:00:00Z"]["is_forecasted"] is False
    assert c_map["2026-01-05T13:00:00Z"]["error_mw"] is None
    assert comp["forecast_run_publish_time_min"] is not None
    assert comp["forecast_run_publish_time_max"] is not None


def test_error_sign_convention(synthetic_db: Path):
    """(c) Test error sign convention: error = forecast - actual (positive = over-forecast)."""
    delivery_date = date(2026, 1, 5)
    comp = compare(delivery_date, cutoff_hour_utc=9, db_path=synthetic_db)
    c_map = {s["start_time"]: s for s in comp["slots"]}

    assert c_map["2026-01-05T10:00:00Z"]["actual_mw"] == 1000.0
    assert c_map["2026-01-05T10:00:00Z"]["forecast_mw"] == 1200.0
    assert c_map["2026-01-05T10:00:00Z"]["error_mw"] == 200.0
    assert c_map["2026-01-05T10:00:00Z"]["abs_error_mw"] == 200.0

    assert c_map["2026-01-05T11:00:00Z"]["actual_mw"] == 2000.0
    assert c_map["2026-01-05T11:00:00Z"]["forecast_mw"] == 1700.0
    assert c_map["2026-01-05T11:00:00Z"]["error_mw"] == -300.0
    assert c_map["2026-01-05T11:00:00Z"]["abs_error_mw"] == 300.0


def test_mae_rmse_bias_and_signed_quantiles(synthetic_db: Path):
    """(d) Test MAE, RMSE, bias, and signed error quantiles against hand-computed values.

    Data errors: [+200, -300, +100].
    Hand calculations:
      bias = (200 - 300 + 100) / 3 = 0.0
      MAE = (200 + 300 + 100) / 3 = 200.0
      RMSE = sqrt((40000 + 90000 + 10000) / 3) = 216.02
      Signed errors sorted: [-300, 100, 200]
      p50 (median) = 100.0
    """
    delivery_date = date(2026, 1, 5)
    res = metrics(delivery_date, delivery_date, cutoff_hour_utc=9, db_path=synthetic_db)

    assert res["n_total_slots"] == 24
    assert res["n_forecasted_slots"] == 3
    assert res["coverage"] == 0.125
    assert res["bias"] == 0.0
    assert res["mae"] == 200.0
    assert res["rmse"] == 216.02
    assert res["p50"] == 100.0
    assert res["p10"] is not None
    assert res["p90"] is not None


def test_horizon_bucketing_excludes_negative_horizons(synthetic_db: Path):
    """(e) Test that metrics_by_horizon strictly excludes negative-horizon rows."""
    delivery_date = date(2026, 1, 5)
    res = metrics_by_horizon(delivery_date, delivery_date, db_path=synthetic_db)

    bucket_map = {b["bucket"]: b for b in res["buckets"]}
    assert bucket_map["24-36h"]["n_forecasts"] == 6
    assert bucket_map["0-6h"]["n_forecasts"] == 0


def test_metrics_by_cutoff_and_daily_and_distribution(synthetic_db: Path):
    """Test by-cutoff metrics, daily metrics, and error distribution."""
    delivery_date = date(2026, 1, 5)

    # by-cutoff
    bc = metrics_by_cutoff(delivery_date, delivery_date, db_path=synthetic_db)
    assert len(bc["by_cutoff"]) == 24
    assert bc["by_cutoff"][9]["cutoff_hour_utc"] == 9
    assert bc["by_cutoff"][9]["mae"] == 200.0

    # daily
    dm = metrics_daily(delivery_date, delivery_date, cutoff_hour_utc=9, db_path=synthetic_db)
    assert len(dm["daily"]) == 1
    assert dm["daily"][0]["delivery_date"] == "2026-01-05"
    assert dm["daily"][0]["mae_mw"] == 200.0

    # error distribution
    ed = error_distribution(delivery_date, delivery_date, cutoff_hour_utc=9, bin_width_mw=500.0, db_path=synthetic_db)
    assert ed["total_count"] == 3
    assert len(ed["bins"]) > 0
