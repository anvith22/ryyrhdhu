"""Pydantic response models for the UK wind forecast evaluation API.

All models document schemas and guarantee type safety across endpoints.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AssumptionsModel(BaseModel):
    timezone: str = Field(..., description="Timezone standard applied across datasets")
    hourly_alignment: str = Field(..., description="Hourly resolution alignment assumption")
    error_convention: str = Field(..., description="Directionality and commercial meaning of forecast error")
    cutoff_rule: str = Field(..., description="Market decision cutoff assumption")
    horizon_definition: str | None = Field(default=None, description="Scope and length of forecast horizon")
    cutoff_timestamp_utc: str | None = Field(default=None, description="Exact UTC cutoff timestamp evaluated")
    metric_notes: str | None = Field(default=None, description="Notes on metric formulation")
    exclusion_rule: str | None = Field(default=None, description="Exclusion criteria applied")


class HealthCoverageDetail(BaseModel):
    count: int
    min_start_time: str | None = None
    max_start_time: str | None = None
    min_date: str | None = None
    max_date: str | None = None
    min_publish_time: str | None = None
    max_publish_time: str | None = None


class HealthResponse(BaseModel):
    status: str
    actuals: HealthCoverageDetail
    forecasts: HealthCoverageDetail
    assumptions: dict[str, Any]


class ActualRecord(BaseModel):
    start_time: str
    generation_mw: float
    settlement_date: str
    settlement_period: int


class ActualsResponse(BaseModel):
    start_date: str
    end_date: str
    count: int
    items: list[ActualRecord]
    assumptions: dict[str, Any]


class ForecastSlot(BaseModel):
    start_time: str
    publish_time: str | None = None
    generation_mw: float | None = None
    horizon_hours: float | None = None


class LatestForecastResponse(BaseModel):
    delivery_date: str
    cutoff_hour_utc: int
    cutoff_time: str
    slots: list[ForecastSlot]
    assumptions: dict[str, Any]


class CompareSummary(BaseModel):
    total_slots: int
    forecasted_slots: int
    coverage: float
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None


class CompareSlot(BaseModel):
    start_time: str
    target_hour_utc: int | None = None
    actual_mw: float | None = None
    forecast_mw: float | None = None
    error_mw: float | None = None
    abs_error_mw: float | None = None
    publish_time: str | None = None
    forecast_publish_time: str | None = None
    horizon_hours: float | None = None
    is_forecasted: bool


class CompareResponse(BaseModel):
    delivery_date: str
    cutoff_hour_utc: int
    cutoff_time: str
    forecast_run_publish_time_min: str | None = None
    forecast_run_publish_time_max: str | None = None
    summary: CompareSummary
    slots: list[CompareSlot]
    assumptions: dict[str, Any]


class MetricsResponse(BaseModel):
    start_date: str
    end_date: str
    cutoff_hour_utc: int
    n_total_slots: int
    n_forecasted_slots: int
    coverage: float
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    p50_abs_error: float | None = None
    p90_abs_error: float | None = None
    p95_abs_error: float | None = None
    # Signed error quantiles (forecast - actual)
    p05: float | None = None
    p10: float | None = None
    p50: float | None = None
    p90: float | None = None
    p95: float | None = None
    mean_actual_mw: float | None = None
    normalized_mae: float | None = None
    assumptions: dict[str, Any]


class HorizonBucket(BaseModel):
    bucket: str
    min_horizon_hours: float
    max_horizon_hours: float | None = None
    n_forecasts: int
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None


class MetricsByHorizonResponse(BaseModel):
    start_date: str
    end_date: str
    buckets: list[HorizonBucket]
    metadata: dict[str, Any]


class HourMetric(BaseModel):
    target_hour_utc: int
    n_slots: int
    mae: float | None = None
    bias: float | None = None
    mean_actual_mw: float | None = None
    mean_forecast_mw: float | None = None


class MetricsByHourResponse(BaseModel):
    start_date: str
    end_date: str
    cutoff_hour_utc: int
    by_hour: list[HourMetric]
    assumptions: dict[str, Any]


class CutoffMetricItem(BaseModel):
    cutoff_hour_utc: int
    cutoff_label: str
    # Like-for-like common-set metrics
    common_mae: float | None = None
    common_rmse: float | None = None
    common_bias: float | None = None
    common_p90_abs_error: float | None = None
    n_common_hours: int = 0
    # Own-coverage metrics
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    p90_abs_error: float | None = None
    coverage: float
    n_forecasted_slots: int
    n_total_slots: int | None = None


class MetricsByCutoffResponse(BaseModel):
    start_date: str
    end_date: str
    n_common_hours: int | None = None
    n_total_possible_hours: int | None = None
    by_cutoff: list[CutoffMetricItem]
    assumptions: dict[str, Any]


class DailyMetricItem(BaseModel):
    delivery_date: str
    mean_actual_mw: float | None = None
    mean_forecast_mw: float | None = None
    bias_mw: float | None = None
    mae_mw: float | None = None
    coverage: float
    forecasted_slots: int
    total_slots: int


class MetricsDailyResponse(BaseModel):
    start_date: str
    end_date: str
    cutoff_hour_utc: int
    daily: list[DailyMetricItem]
    assumptions: dict[str, Any]


class ErrorDistributionBin(BaseModel):
    bin_start: float
    bin_end: float
    bin_label: str
    count: int


class ErrorDistributionResponse(BaseModel):
    start_date: str
    end_date: str
    cutoff_hour_utc: int
    bin_width_mw: float
    total_count: int
    bins: list[ErrorDistributionBin]
    assumptions: dict[str, Any]
