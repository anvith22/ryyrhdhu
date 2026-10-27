"""Services package exports."""

from backend.app.services.forecast_service import (
    ASSUMPTIONS_META,
    compare,
    error_distribution,
    generate_day_hourly_slots,
    get_actuals,
    get_data_coverage_bounds,
    get_hourly_actuals_map,
    metrics,
    metrics_by_cutoff,
    metrics_by_horizon,
    metrics_by_hour_of_day,
    metrics_daily,
    select_latest_forecasts,
)

__all__ = [
    "ASSUMPTIONS_META",
    "compare",
    "error_distribution",
    "generate_day_hourly_slots",
    "get_actuals",
    "get_data_coverage_bounds",
    "get_hourly_actuals_map",
    "metrics",
    "metrics_by_cutoff",
    "metrics_by_horizon",
    "metrics_by_hour_of_day",
    "metrics_daily",
    "select_latest_forecasts",
]
