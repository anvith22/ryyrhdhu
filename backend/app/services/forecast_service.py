"""Business logic services for UK wind generation forecast evaluation.

Evaluates forecast accuracy at HOURLY resolution to match WINDFOR's hourly granularity:
- Forecast with startTime T covers the hour starting at T: [T, T + 1h).
- Hourly actual is computed as the arithmetic mean of the two half-hour FUELHH actuals in that hour.
- Half-hourly actuals remain accessible via get_actuals() for high-resolution charting.
- Coverage is defined as forecasted_hours / total_hours (unforecasted means no eligible forecast).
- Error convention: error = forecast - actual (positive = over-forecast; buyer under-procures
  on day-ahead and is exposed to balancing/imbalance cash-out costs as a short position).
- All operations execute in UTC. In January, UK local time (GMT) equals UTC.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.ingest.storage import DEFAULT_DB_PATH, get_sqlite_connection

ASSUMED_GATE_CLOSURE_HOUR_UTC = 9

ASSUMPTIONS_META = {
    "timezone": "UTC (In January, Great Britain local time GMT equals UTC)",
    "hourly_alignment": (
        "Evaluated at hourly resolution. A forecast with startTime T covers the 1-hour interval [T, T+1h). "
        "actual_hourly is the arithmetic mean of the two half-hour FUELHH actuals in that hour."
    ),
    "error_convention": (
        "error = forecast - actual (positive values indicate over-forecast; "
        "buyer under-procures on day-ahead and is exposed to balancing/imbalance costs as a short position)"
    ),
    "cutoff_rule": "For delivery day D, latest forecast published on or before D-1 at cutoff_hour:00 UTC",
    "assumed_gate_closure_hour_utc": ASSUMED_GATE_CLOSURE_HOUR_UTC,
    "gate_closure_note": "ASSUMED_GATE_CLOSURE_HOUR_UTC = 9 (documented as an unverified operational assumption).",
    "horizon_definition": "WINDFOR forecast runs provide a 72-hour horizon (73 hourly steps from 0h to 72h).",
    "scope_caveat": (
        "The positive bias is persistent across horizons and days, may partly reflect scope differences "
        "(FUELHH covers metered units and Elexon notes embedded/unmetered wind is excluded) and partly forecast error, "
        "and available data cannot separate the two. The daily ratio varies widely (22 of 31 days within [1.07, 1.35], "
        "min 0.89, max 1.93, median 1.14), so a constant-scope explanation alone is not supported."
    ),
}


def get_data_coverage_bounds(db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Retrieve date bounds and record counts from the database snapshot."""
    conn = get_sqlite_connection(db_path)
    try:
        actuals_row = conn.execute("""
            SELECT MIN(start_time) as min_start, MAX(start_time) as max_start, COUNT(*) as count
            FROM actuals_wind;
        """).fetchone()

        forecasts_row = conn.execute("""
            SELECT MIN(start_time) as min_start, MAX(start_time) as max_start,
                   MIN(publish_time) as min_pub, MAX(publish_time) as max_pub,
                   COUNT(*) as count
            FROM forecasts_wind;
        """).fetchone()

        min_actual_date = (
            datetime.fromisoformat(actuals_row["min_start"]).date() if actuals_row["min_start"] else None
        )
        max_actual_date = (
            datetime.fromisoformat(actuals_row["max_start"]).date() if actuals_row["max_start"] else None
        )

        return {
            "actuals": {
                "count": actuals_row["count"],
                "min_start_time": actuals_row["min_start"],
                "max_start_time": actuals_row["max_start"],
                "min_date": min_actual_date.isoformat() if min_actual_date else None,
                "max_date": max_actual_date.isoformat() if max_actual_date else None,
            },
            "forecasts": {
                "count": forecasts_row["count"],
                "min_start_time": forecasts_row["min_start"],
                "max_start_time": forecasts_row["max_start"],
                "min_publish_time": forecasts_row["min_pub"],
                "max_publish_time": forecasts_row["max_pub"],
            },
        }
    finally:
        conn.close()


def generate_day_hourly_slots(delivery_date: date) -> list[str]:
    """Generate all 24 hourly slot timestamps for a delivery date in UTC."""
    slots = []
    base_dt = datetime.combine(delivery_date, time(0, 0), tzinfo=timezone.utc)
    for i in range(24):
        slot_dt = base_dt + timedelta(hours=i)
        slots.append(slot_dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return slots


def get_actuals(
    start_date: date,
    end_date: date,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Retrieve raw half-hourly actual wind generation records (FUELHH WIND) for charting."""
    day_start = datetime.combine(start_date, time(0, 0), tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    day_end = datetime.combine(end_date, time(23, 30), tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = get_sqlite_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT start_time, generation_mw, settlement_date, settlement_period
            FROM actuals_wind
            WHERE start_time >= :day_start AND start_time <= :day_end
            ORDER BY start_time ASC;
            """,
            {"day_start": day_start, "day_end": day_end},
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_hourly_actuals_map(
    start_date: date,
    end_date: date,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, float]:
    """Calculate hourly actual wind generation by averaging the two 30-min actuals in each hour."""
    raw_actuals = get_actuals(start_date, end_date, db_path=db_path)
    if not raw_actuals:
        return {}

    hourly_buckets: dict[str, list[float]] = {}
    for r in raw_actuals:
        dt = datetime.fromisoformat(r["start_time"])
        hour_dt = dt.replace(minute=0, second=0, microsecond=0)
        hour_str = hour_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        hourly_buckets.setdefault(hour_str, []).append(r["generation_mw"])

    return {hour_str: float(np.mean(vals)) for hour_str, vals in hourly_buckets.items() if vals}


def select_latest_forecasts(
    delivery_date: date,
    cutoff_hour_utc: int = 9,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Select the latest available forecast for each of the 24 hourly slots on delivery_date.

    Cutoff is defined as (delivery_date - 1 day) at cutoff_hour_utc:00 UTC.
    For each target hour, chooses the row with max publish_time <= cutoff.
    Hours with no eligible forecast are returned as unforecasted (null), never filled.
    """
    if not (0 <= cutoff_hour_utc <= 23):
        raise ValueError(f"cutoff_hour_utc must be between 0 and 23, got {cutoff_hour_utc}")

    cutoff_dt = datetime.combine(delivery_date - timedelta(days=1), time(cutoff_hour_utc, 0), tzinfo=timezone.utc)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    hourly_slots = generate_day_hourly_slots(delivery_date)
    day_start = hourly_slots[0]
    day_end = hourly_slots[-1]

    conn = get_sqlite_connection(db_path)
    try:
        query = """
            WITH ranked AS (
                SELECT
                    start_time,
                    publish_time,
                    generation_mw,
                    horizon_hours,
                    ROW_NUMBER() OVER (
                        PARTITION BY start_time
                        ORDER BY publish_time DESC
                    ) as rn
                FROM forecasts_wind
                WHERE start_time >= :day_start
                  AND start_time <= :day_end
                  AND publish_time <= :cutoff_str
            )
            SELECT start_time, publish_time, generation_mw, horizon_hours
            FROM ranked
            WHERE rn = 1;
        """
        rows = conn.execute(
            query,
            {"day_start": day_start, "day_end": day_end, "cutoff_str": cutoff_str},
        ).fetchall()
        forecast_map = {row["start_time"]: dict(row) for row in rows}
    finally:
        conn.close()

    results = []
    for slot in hourly_slots:
        if slot in forecast_map:
            results.append(forecast_map[slot])
        else:
            results.append({
                "start_time": slot,
                "publish_time": None,
                "generation_mw": None,
                "horizon_hours": None,
            })

    return results


def compare(
    delivery_date: date,
    cutoff_hour_utc: int = 9,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Join selected latest forecasts with hourly actuals for delivery_date."""
    cutoff_dt = datetime.combine(delivery_date - timedelta(days=1), time(cutoff_hour_utc, 0), tzinfo=timezone.utc)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    selected_forecasts = select_latest_forecasts(delivery_date, cutoff_hour_utc, db_path=db_path)
    hourly_actuals = get_hourly_actuals_map(delivery_date, delivery_date, db_path=db_path)

    slots_comparison = []
    errors = []
    abs_errors = []
    valid_publish_times = []

    for f_slot in selected_forecasts:
        slot_time = f_slot["start_time"]
        act_mw = hourly_actuals.get(slot_time)
        fc_mw = f_slot["generation_mw"]
        pub_time = f_slot["publish_time"]
        horizon = f_slot["horizon_hours"]

        if pub_time is not None:
            valid_publish_times.append(pub_time)

        if fc_mw is not None and act_mw is not None:
            err = fc_mw - act_mw
            abs_err = abs(err)
            errors.append(err)
            abs_errors.append(abs_err)
        else:
            err = None
            abs_err = None

        target_dt = datetime.fromisoformat(slot_time)

        slots_comparison.append({
            "start_time": slot_time,
            "target_hour_utc": target_dt.hour,
            "actual_mw": round(act_mw, 2) if act_mw is not None else None,
            "forecast_mw": round(fc_mw, 2) if fc_mw is not None else None,
            "error_mw": round(err, 2) if err is not None else None,
            "abs_error_mw": round(abs_err, 2) if abs_err is not None else None,
            "publish_time": pub_time,
            "forecast_publish_time": pub_time,
            "horizon_hours": horizon,
            "is_forecasted": fc_mw is not None,
        })

    n_forecasted = len(errors)
    total_hours = len(slots_comparison)
    summary = {
        "total_slots": total_hours,
        "forecasted_slots": n_forecasted,
        "coverage": round(n_forecasted / total_hours, 4) if total_hours > 0 else 0.0,
        "mae": round(float(np.mean(abs_errors)), 2) if abs_errors else None,
        "rmse": round(float(np.sqrt(np.mean(np.square(errors)))), 2) if errors else None,
        "bias": round(float(np.mean(errors)), 2) if errors else None,
    }

    min_pub = min(valid_publish_times) if valid_publish_times else None
    max_pub = max(valid_publish_times) if valid_publish_times else None

    return {
        "delivery_date": delivery_date.isoformat(),
        "cutoff_time": cutoff_str,
        "cutoff_hour_utc": cutoff_hour_utc,
        "forecast_run_publish_time_min": min_pub,
        "forecast_run_publish_time_max": max_pub,
        "summary": summary,
        "slots": slots_comparison,
        "assumptions": {
            **ASSUMPTIONS_META,
            "cutoff_timestamp_utc": cutoff_str,
        },
    }


def metrics(
    start_date: date,
    end_date: date,
    cutoff_hour_utc: int = 9,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Aggregate accuracy metrics across all delivery days at hourly resolution.

    Includes signed-error quantiles (p05, p10, p50, p90, p95) as well as absolute error quantiles.
    """
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")

    total_possible_hours = 0
    all_errors = []
    all_abs_errors = []
    all_actuals = []

    curr_date = start_date
    while curr_date <= end_date:
        cmp_result = compare(curr_date, cutoff_hour_utc, db_path=db_path)
        for s in cmp_result["slots"]:
            total_possible_hours += 1
            if s["is_forecasted"] and s["actual_mw"] is not None:
                err = s["error_mw"]
                all_errors.append(err)
                all_abs_errors.append(abs(err))
                all_actuals.append(s["actual_mw"])
        curr_date += timedelta(days=1)

    n_forecasted = len(all_errors)
    coverage = round(n_forecasted / total_possible_hours, 4) if total_possible_hours > 0 else 0.0

    if n_forecasted > 0:
        mae = float(np.mean(all_abs_errors))
        rmse = float(np.sqrt(np.mean(np.square(all_errors))))
        bias = float(np.mean(all_errors))

        # Absolute error quantiles
        p50_abs = float(np.percentile(all_abs_errors, 50))
        p90_abs = float(np.percentile(all_abs_errors, 90))
        p95_abs = float(np.percentile(all_abs_errors, 95))

        # Signed error quantiles (forecast - actual)
        p05_signed = float(np.percentile(all_errors, 5))
        p10_signed = float(np.percentile(all_errors, 10))
        p50_signed = float(np.percentile(all_errors, 50))
        p90_signed = float(np.percentile(all_errors, 90))
        p95_signed = float(np.percentile(all_errors, 95))

        mean_actual = float(np.mean(all_actuals))
        norm_mae = float(mae / mean_actual) if mean_actual > 0 else None
    else:
        mae = rmse = bias = p50_abs = p90_abs = p95_abs = None
        p05_signed = p10_signed = p50_signed = p90_signed = p95_signed = None
        mean_actual = norm_mae = None

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "cutoff_hour_utc": cutoff_hour_utc,
        "n_total_slots": total_possible_hours,
        "n_forecasted_slots": n_forecasted,
        "coverage": coverage,
        "mae": round(mae, 2) if mae is not None else None,
        "rmse": round(rmse, 2) if rmse is not None else None,
        "bias": round(bias, 2) if bias is not None else None,
        "p50_abs_error": round(p50_abs, 2) if p50_abs is not None else None,
        "p90_abs_error": round(p90_abs, 2) if p90_abs is not None else None,
        "p95_abs_error": round(p95_abs, 2) if p95_abs is not None else None,
        # Signed error quantiles for plausible actual prediction intervals
        "p05": round(p05_signed, 2) if p05_signed is not None else None,
        "p10": round(p10_signed, 2) if p10_signed is not None else None,
        "p50": round(p50_signed, 2) if p50_signed is not None else None,
        "p90": round(p90_signed, 2) if p90_signed is not None else None,
        "p95": round(p95_signed, 2) if p95_signed is not None else None,
        "mean_actual_mw": round(mean_actual, 2) if mean_actual is not None else None,
        "normalized_mae": round(norm_mae, 4) if norm_mae is not None else None,
        "assumptions": {
            **ASSUMPTIONS_META,
            "metric_notes": (
                "Evaluated on hourly resolution (24 slots/day). "
                "MAPE omitted due to near-zero denominator instability. "
                "Normalized MAE = MAE / mean_actual. "
                "p05..p95 are signed error percentiles (forecast - actual)."
            ),
        },
    }


def metrics_by_cutoff(
    start_date: date,
    end_date: date,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Compute accuracy metrics across cutoff hours 0..23 on D-1.

    Returns both:
    1. Like-for-like common-set metrics evaluated on the identical set of delivery
       hours with eligible forecasts at ALL 24 cutoff hours.
    2. Per-cutoff own-coverage metrics evaluated on all eligible forecasts for that hour.
    """
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")

    cutoff_errors: dict[int, dict[str, float]] = {h: {} for h in range(24)}
    cutoff_abs_errors: dict[int, dict[str, float]] = {h: {} for h in range(24)}
    total_slots = 0

    curr_date = start_date
    while curr_date <= end_date:
        for _ in range(24):
            total_slots += 1
        for h in range(24):
            cmp_res = compare(curr_date, cutoff_hour_utc=h, db_path=db_path)
            for s in cmp_res["slots"]:
                if s["is_forecasted"] and s["error_mw"] is not None:
                    st = s["start_time"]
                    cutoff_errors[h][st] = s["error_mw"]
                    cutoff_abs_errors[h][st] = abs(s["error_mw"])
        curr_date += timedelta(days=1)

    # Common set of delivery slots that have an eligible forecast across ALL 24 cutoffs
    if cutoff_errors and all(len(cutoff_errors[h]) > 0 for h in range(24)):
        common_start_times = set.intersection(*(set(cutoff_errors[h].keys()) for h in range(24)))
    else:
        common_start_times = set()
    n_common_hours = len(common_start_times)

    by_cutoff = []
    for h in range(24):
        # 1. Own set metrics
        own_errs = list(cutoff_errors[h].values())
        own_abs = list(cutoff_abs_errors[h].values())
        n_own = len(own_errs)
        cov = round(n_own / total_slots, 4) if total_slots > 0 else 0.0

        if n_own > 0:
            own_mae = round(float(np.mean(own_abs)), 2)
            own_rmse = round(float(np.sqrt(np.mean(np.square(own_errs)))), 2)
            own_bias = round(float(np.mean(own_errs)), 2)
            own_p90 = round(float(np.percentile(own_abs, 90)), 2)
        else:
            own_mae = own_rmse = own_bias = own_p90 = None

        # 2. Common set (like-for-like) metrics
        if n_common_hours > 0:
            comm_errs = [cutoff_errors[h][st] for st in common_start_times]
            comm_abs = [cutoff_abs_errors[h][st] for st in common_start_times]
            comm_mae = round(float(np.mean(comm_abs)), 2)
            comm_rmse = round(float(np.sqrt(np.mean(np.square(comm_errs)))), 2)
            comm_bias = round(float(np.mean(comm_errs)), 2)
            comm_p90 = round(float(np.percentile(comm_abs, 90)), 2)
        else:
            comm_mae = comm_rmse = comm_bias = comm_p90 = None

        by_cutoff.append({
            "cutoff_hour_utc": h,
            "cutoff_label": f"D-1 {h:02d}:00 UTC",
            # Like-for-like common-set metrics
            "common_mae": comm_mae,
            "common_rmse": comm_rmse,
            "common_bias": comm_bias,
            "common_p90_abs_error": comm_p90,
            "n_common_hours": n_common_hours,
            # Per-cutoff own-coverage metrics
            "mae": own_mae,
            "rmse": own_rmse,
            "bias": own_bias,
            "p90_abs_error": own_p90,
            "coverage": cov,
            "n_forecasted_slots": n_own,
            "n_total_slots": total_slots,
        })

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "n_common_hours": n_common_hours,
        "n_total_possible_hours": total_slots,
        "by_cutoff": by_cutoff,
        "assumptions": {
            **ASSUMPTIONS_META,
            "description": (
                "Accuracy metrics evaluated for each decision cutoff hour 00:00 to 23:00 UTC on D-1. "
                "Provides both like-for-like common-set metrics (evaluated on the identical set of hours "
                "forecasted across all cutoffs) and per-cutoff own-coverage metrics."
            ),
        },
    }


def metrics_daily(
    start_date: date,
    end_date: date,
    cutoff_hour_utc: int = 9,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Compute per-delivery-day accuracy metrics for each day in range."""
    daily_list = []
    curr_date = start_date

    while curr_date <= end_date:
        cmp_res = compare(curr_date, cutoff_hour_utc, db_path=db_path)
        s_list = cmp_res["slots"]
        acts = [s["actual_mw"] for s in s_list if s["is_forecasted"] and s["actual_mw"] is not None]
        fcs = [s["forecast_mw"] for s in s_list if s["is_forecasted"] and s["forecast_mw"] is not None]
        errs = [s["error_mw"] for s in s_list if s["is_forecasted"] and s["error_mw"] is not None]
        abs_errs = [s["abs_error_mw"] for s in s_list if s["is_forecasted"] and s["abs_error_mw"] is not None]

        daily_list.append({
            "delivery_date": curr_date.isoformat(),
            "mean_actual_mw": round(float(np.mean(acts)), 2) if acts else None,
            "mean_forecast_mw": round(float(np.mean(fcs)), 2) if fcs else None,
            "bias_mw": round(float(np.mean(errs)), 2) if errs else None,
            "mae_mw": round(float(np.mean(abs_errs)), 2) if abs_errs else None,
            "coverage": cmp_res["summary"]["coverage"],
            "forecasted_slots": cmp_res["summary"]["forecasted_slots"],
            "total_slots": cmp_res["summary"]["total_slots"],
        })
        curr_date += timedelta(days=1)

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "cutoff_hour_utc": cutoff_hour_utc,
        "daily": daily_list,
        "assumptions": {
            **ASSUMPTIONS_META,
            "description": "Daily aggregated mean actual, mean forecast, bias, and MAE at hourly resolution.",
        },
    }


def error_distribution(
    start_date: date,
    end_date: date,
    cutoff_hour_utc: int = 9,
    bin_width_mw: float = 500.0,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Calculate histogram bins of signed hourly errors (forecast - actual)."""
    curr_date = start_date
    all_errors = []

    while curr_date <= end_date:
        cmp_res = compare(curr_date, cutoff_hour_utc, db_path=db_path)
        for s in cmp_res["slots"]:
            if s["is_forecasted"] and s["error_mw"] is not None:
                all_errors.append(s["error_mw"])
        curr_date += timedelta(days=1)

    if not all_errors:
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "cutoff_hour_utc": cutoff_hour_utc,
            "bin_width_mw": bin_width_mw,
            "total_count": 0,
            "bins": [],
            "assumptions": ASSUMPTIONS_META,
        }

    min_err = float(np.min(all_errors))
    max_err = float(np.max(all_errors))

    # Determine uniform bin edges aligned to bin_width_mw
    start_edge = math.floor(min_err / bin_width_mw) * bin_width_mw
    end_edge = math.ceil(max_err / bin_width_mw) * bin_width_mw

    num_bins = max(1, int(round((end_edge - start_edge) / bin_width_mw)))
    bin_edges = [start_edge + i * bin_width_mw for i in range(num_bins + 1)]

    counts, _ = np.histogram(all_errors, bins=bin_edges)

    bins_result = []
    for i in range(num_bins):
        b_start = bin_edges[i]
        b_end = bin_edges[i + 1]
        bins_result.append({
            "bin_start": round(b_start, 1),
            "bin_end": round(b_end, 1),
            "bin_label": f"{int(b_start):+d} to {int(b_end):+d} MW",
            "count": int(counts[i]),
        })

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "cutoff_hour_utc": cutoff_hour_utc,
        "bin_width_mw": bin_width_mw,
        "total_count": len(all_errors),
        "bins": bins_result,
        "assumptions": ASSUMPTIONS_META,
    }


def metrics_by_horizon(
    start_date: date,
    end_date: date,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Bucket all forward forecasts by forecast horizon (hours) and compute accuracy metrics."""
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")

    hourly_actuals = get_hourly_actuals_map(start_date, end_date, db_path=db_path)
    day_start = datetime.combine(start_date, time(0, 0), tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    day_end = datetime.combine(end_date, time(23, 0), tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = get_sqlite_connection(db_path)
    try:
        query = """
            SELECT
                start_time,
                publish_time,
                generation_mw as forecast_mw,
                horizon_hours
            FROM forecasts_wind
            WHERE start_time >= :day_start
              AND start_time <= :day_end
              AND horizon_hours > 0;
        """
        rows = conn.execute(query, {"day_start": day_start, "day_end": day_end}).fetchall()
        df = pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()

    bucket_definitions = [
        ("0-6h", 0.0, 6.0),
        ("6-12h", 6.0, 12.0),
        ("12-24h", 12.0, 24.0),
        ("24-36h", 24.0, 36.0),
        ("36-48h", 36.0, 48.0),
        ("48h+", 48.0, 1000.0),
    ]

    buckets_result = []

    if not df.empty and hourly_actuals:
        df["actual_mw"] = df["start_time"].map(hourly_actuals)
        df = df.dropna(subset=["actual_mw"]).copy()

        df["error"] = df["forecast_mw"] - df["actual_mw"]
        df["abs_error"] = df["error"].abs()

        for label, low, high in bucket_definitions:
            if label == "48h+":
                mask = df["horizon_hours"] > low
            else:
                mask = (df["horizon_hours"] > low) & (df["horizon_hours"] <= high)

            b_df = df[mask]
            if not b_df.empty:
                mae = float(b_df["abs_error"].mean())
                rmse = float(np.sqrt((b_df["error"] ** 2).mean()))
                bias = float(b_df["error"].mean())
                n_count = len(b_df)
            else:
                mae = rmse = bias = None
                n_count = 0

            buckets_result.append({
                "bucket": label,
                "min_horizon_hours": low,
                "max_horizon_hours": high if high < 1000.0 else None,
                "n_forecasts": n_count,
                "mae": round(mae, 2) if mae is not None else None,
                "rmse": round(rmse, 2) if rmse is not None else None,
                "bias": round(bias, 2) if bias is not None else None,
            })
    else:
        for label, low, high in bucket_definitions:
            buckets_result.append({
                "bucket": label,
                "min_horizon_hours": low,
                "max_horizon_hours": high if high < 1000.0 else None,
                "n_forecasts": 0,
                "mae": None,
                "rmse": None,
                "bias": None,
            })

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "buckets": buckets_result,
        "metadata": {
            **ASSUMPTIONS_META,
            "exclusion_rule": (
                "Negative-horizon rows (publish_time > start_time) are strictly excluded from horizon evaluation. "
                "Forecast horizons in WINDFOR span up to 72 hours (73 hourly steps from 0h to 72h)."
            ),
        },
    }


def metrics_by_hour_of_day(
    start_date: date,
    end_date: date,
    cutoff_hour_utc: int = 9,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Calculate MAE and bias grouped by target delivery hour (0 through 23 UTC) at hourly resolution."""
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")

    hour_errors: dict[int, list[float]] = {h: [] for h in range(24)}
    hour_abs_errors: dict[int, list[float]] = {h: [] for h in range(24)}
    hour_actuals: dict[int, list[float]] = {h: [] for h in range(24)}
    hour_forecasts: dict[int, list[float]] = {h: [] for h in range(24)}

    curr_date = start_date
    while curr_date <= end_date:
        cmp_result = compare(curr_date, cutoff_hour_utc, db_path=db_path)
        for s in cmp_result["slots"]:
            if s["is_forecasted"] and s["actual_mw"] is not None:
                h = s["target_hour_utc"]
                err = s["error_mw"]
                hour_errors[h].append(err)
                hour_abs_errors[h].append(abs(err))
                hour_actuals[h].append(s["actual_mw"])
                hour_forecasts[h].append(s["forecast_mw"])
        curr_date += timedelta(days=1)

    by_hour = []
    for h in range(24):
        errs = hour_errors[h]
        if errs:
            mae = float(np.mean(hour_abs_errors[h]))
            bias = float(np.mean(errs))
            mean_act = float(np.mean(hour_actuals[h]))
            mean_fc = float(np.mean(hour_forecasts[h]))
            n_slots = len(errs)
        else:
            mae = bias = mean_act = mean_fc = None
            n_slots = 0

        by_hour.append({
            "target_hour_utc": h,
            "n_slots": n_slots,
            "mae": round(mae, 2) if mae is not None else None,
            "bias": round(bias, 2) if bias is not None else None,
            "mean_actual_mw": round(mean_act, 2) if mean_act is not None else None,
            "mean_forecast_mw": round(mean_fc, 2) if mean_fc is not None else None,
        })

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "cutoff_hour_utc": cutoff_hour_utc,
        "by_hour": by_hour,
        "assumptions": {
            **ASSUMPTIONS_META,
            "grouping": "Aggregated by target delivery hour 00:00 to 23:00 UTC",
        },
    }
