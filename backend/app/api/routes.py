"""FastAPI routes for UK wind generation and forecast evaluation API."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.api.schemas import (
    ActualsResponse,
    CompareResponse,
    ErrorDistributionResponse,
    HealthResponse,
    LatestForecastResponse,
    MetricsByCutoffResponse,
    MetricsByHorizonResponse,
    MetricsByHourResponse,
    MetricsDailyResponse,
    MetricsResponse,
)
from backend.app.services.forecast_service import (
    ASSUMPTIONS_META,
    compare,
    error_distribution,
    get_actuals,
    get_data_coverage_bounds,
    metrics,
    metrics_by_cutoff,
    metrics_by_horizon,
    metrics_by_hour_of_day,
    metrics_daily,
    select_latest_forecasts,
)

router = APIRouter(prefix="/api", tags=["wind-forecast"])


def _validate_date_in_range(d: date, bounds: dict, field_name: str) -> None:
    """Validate that requested date is within the snapshot coverage."""
    min_str = bounds["actuals"]["min_date"]
    max_str = bounds["actuals"]["max_date"]
    if not min_str or not max_str:
        return

    min_date = date.fromisoformat(min_str)
    max_date = date.fromisoformat(max_str)
    if d < min_date or d > max_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Requested {field_name} '{d}' is outside available snapshot bounds "
                f"({min_date} to {max_date})."
            ),
        )


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """System health check and ingested database coverage overview."""
    bounds = get_data_coverage_bounds()
    return HealthResponse(
        status="healthy",
        actuals=bounds["actuals"],
        forecasts=bounds["forecasts"],
        assumptions=ASSUMPTIONS_META,
    )


@router.get("/actuals", response_model=ActualsResponse)
def get_actuals_route(
    start: Annotated[date, Query(description="Start settlement date (YYYY-MM-DD)")],
    end: Annotated[date, Query(description="End settlement date (YYYY-MM-DD)")],
) -> ActualsResponse:
    """Retrieve actual half-hourly wind generation records (FUELHH WIND)."""
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"start date ({start}) cannot be after end date ({end})",
        )

    bounds = get_data_coverage_bounds()
    _validate_date_in_range(start, bounds, "start")
    _validate_date_in_range(end, bounds, "end")

    items = get_actuals(start, end)
    return ActualsResponse(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        count=len(items),
        items=items,
        assumptions=ASSUMPTIONS_META,
    )


@router.get("/forecast/latest", response_model=LatestForecastResponse)
def get_latest_forecast_route(
    delivery_date: Annotated[date, Query(description="Target delivery date (YYYY-MM-DD)")],
    cutoff_hour: Annotated[
        int,
        Query(ge=0, le=23, description="D-1 decision cutoff hour in UTC (0-23)"),
    ] = 9,
) -> LatestForecastResponse:
    """Retrieve latest available forecast per hourly slot on delivery_date based on D-1 cutoff."""
    bounds = get_data_coverage_bounds()
    _validate_date_in_range(delivery_date, bounds, "delivery_date")

    slots = select_latest_forecasts(delivery_date, cutoff_hour_utc=cutoff_hour)
    cutoff_dt_str = f"{(delivery_date).isoformat()} (Cutoff: D-1 at {cutoff_hour:02d}:00 UTC)"

    return LatestForecastResponse(
        delivery_date=delivery_date.isoformat(),
        cutoff_hour_utc=cutoff_hour,
        cutoff_time=cutoff_dt_str,
        slots=slots,
        assumptions={
            **ASSUMPTIONS_META,
            "cutoff_hour_utc": cutoff_hour,
        },
    )


@router.get("/compare", response_model=CompareResponse)
def get_compare_route(
    delivery_date: Annotated[date, Query(description="Target delivery date (YYYY-MM-DD)")],
    cutoff_hour: Annotated[
        int,
        Query(ge=0, le=23, description="D-1 decision cutoff hour in UTC (0-23)"),
    ] = 9,
) -> CompareResponse:
    """Compare selected latest forecasts against hourly actual generation for delivery_date."""
    bounds = get_data_coverage_bounds()
    _validate_date_in_range(delivery_date, bounds, "delivery_date")

    result = compare(delivery_date, cutoff_hour_utc=cutoff_hour)
    return CompareResponse(**result)


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics_route(
    start: Annotated[date, Query(description="Start delivery date (YYYY-MM-DD)")],
    end: Annotated[date, Query(description="End delivery date (YYYY-MM-DD)")],
    cutoff_hour: Annotated[
        int,
        Query(ge=0, le=23, description="D-1 decision cutoff hour in UTC (0-23)"),
    ] = 9,
) -> MetricsResponse:
    """Compute aggregate accuracy metrics (MAE, RMSE, bias, P05..P95 signed quantiles) over a date range."""
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"start date ({start}) cannot be after end date ({end})",
        )

    bounds = get_data_coverage_bounds()
    _validate_date_in_range(start, bounds, "start")
    _validate_date_in_range(end, bounds, "end")

    res = metrics(start, end, cutoff_hour_utc=cutoff_hour)
    return MetricsResponse(**res)


@router.get("/metrics/by-cutoff", response_model=MetricsByCutoffResponse)
def get_metrics_by_cutoff_route(
    start: Annotated[date, Query(description="Start delivery date (YYYY-MM-DD)")],
    end: Annotated[date, Query(description="End delivery date (YYYY-MM-DD)")],
) -> MetricsByCutoffResponse:
    """Evaluate accuracy metrics across D-1 decision cutoff hours 0..23."""
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"start date ({start}) cannot be after end date ({end})",
        )

    bounds = get_data_coverage_bounds()
    _validate_date_in_range(start, bounds, "start")
    _validate_date_in_range(end, bounds, "end")

    res = metrics_by_cutoff(start, end)
    return MetricsByCutoffResponse(**res)


@router.get("/metrics/daily", response_model=MetricsDailyResponse)
def get_metrics_daily_route(
    start: Annotated[date, Query(description="Start delivery date (YYYY-MM-DD)")],
    end: Annotated[date, Query(description="End delivery date (YYYY-MM-DD)")],
    cutoff_hour: Annotated[
        int,
        Query(ge=0, le=23, description="D-1 decision cutoff hour in UTC (0-23)"),
    ] = 9,
) -> MetricsDailyResponse:
    """Retrieve per-delivery-day mean actual, mean forecast, bias, and MAE across date range."""
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"start date ({start}) cannot be after end date ({end})",
        )

    bounds = get_data_coverage_bounds()
    _validate_date_in_range(start, bounds, "start")
    _validate_date_in_range(end, bounds, "end")

    res = metrics_daily(start, end, cutoff_hour_utc=cutoff_hour)
    return MetricsDailyResponse(**res)


@router.get("/error-distribution", response_model=ErrorDistributionResponse)
def get_error_distribution_route(
    start: Annotated[date, Query(description="Start delivery date (YYYY-MM-DD)")],
    end: Annotated[date, Query(description="End delivery date (YYYY-MM-DD)")],
    cutoff_hour: Annotated[
        int,
        Query(ge=0, le=23, description="D-1 decision cutoff hour in UTC (0-23)"),
    ] = 9,
) -> ErrorDistributionResponse:
    """Retrieve histogram bins of signed hourly errors (forecast - actual) in 500 MW bins."""
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"start date ({start}) cannot be after end date ({end})",
        )

    bounds = get_data_coverage_bounds()
    _validate_date_in_range(start, bounds, "start")
    _validate_date_in_range(end, bounds, "end")

    res = error_distribution(start, end, cutoff_hour_utc=cutoff_hour)
    return ErrorDistributionResponse(**res)


@router.get("/metrics/by-horizon", response_model=MetricsByHorizonResponse)
def get_metrics_by_horizon_route(
    start: Annotated[date, Query(description="Start delivery date (YYYY-MM-DD)")],
    end: Annotated[date, Query(description="End delivery date (YYYY-MM-DD)")],
) -> MetricsByHorizonResponse:
    """Bucket all forward forecasts by forecast horizon (hours) and compute MAE, RMSE, and bias."""
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"start date ({start}) cannot be after end date ({end})",
        )

    bounds = get_data_coverage_bounds()
    _validate_date_in_range(start, bounds, "start")
    _validate_date_in_range(end, bounds, "end")

    res = metrics_by_horizon(start, end)
    return MetricsByHorizonResponse(**res)


@router.get("/metrics/by-hour", response_model=MetricsByHourResponse)
def get_metrics_by_hour_route(
    start: Annotated[date, Query(description="Start delivery date (YYYY-MM-DD)")],
    end: Annotated[date, Query(description="End delivery date (YYYY-MM-DD)")],
    cutoff_hour: Annotated[
        int,
        Query(ge=0, le=23, description="D-1 decision cutoff hour in UTC (0-23)"),
    ] = 9,
) -> MetricsByHourResponse:
    """Compute MAE and bias grouped by target delivery hour (0 through 23 UTC)."""
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"start date ({start}) cannot be after end date ({end})",
        )

    bounds = get_data_coverage_bounds()
    _validate_date_in_range(start, bounds, "start")
    _validate_date_in_range(end, bounds, "end")

    res = metrics_by_hour_of_day(start, end, cutoff_hour_utc=cutoff_hour)
    return MetricsByHourResponse(**res)
