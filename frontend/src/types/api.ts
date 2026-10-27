/**
 * TypeScript API interfaces matching backend Pydantic schemas.
 * All timestamps are in UTC ISO-8601 format.
 */

export interface AssumptionsMeta {
  timezone: string;
  hourly_alignment: string;
  error_convention: string;
  cutoff_rule: string;
  horizon_definition?: string;
  cutoff_timestamp_utc?: string;
  metric_notes?: string;
  exclusion_rule?: string;
  [key: string]: any;
}

export interface HealthResponse {
  status: string;
  actuals: {
    count: number;
    min_start_time: string | null;
    max_start_time: string | null;
    min_date: string | null;
    max_date: string | null;
  };
  forecasts: {
    count: number;
    min_start_time: string | null;
    max_start_time: string | null;
    min_publish_time: string | null;
    max_publish_time: string | null;
  };
  assumptions: AssumptionsMeta;
}

export interface ActualRecord {
  start_time: string;
  generation_mw: number;
  settlement_date: string;
  settlement_period: number;
}

export interface ActualsResponse {
  start_date: string;
  end_date: string;
  count: number;
  items: ActualRecord[];
  assumptions: AssumptionsMeta;
}

export interface CompareSlot {
  start_time: string;
  target_hour_utc: number;
  actual_mw: number | null;
  forecast_mw: number | null;
  error_mw: number | null;
  abs_error_mw: number | null;
  publish_time: string | null;
  forecast_publish_time?: string | null;
  horizon_hours: number | null;
  is_forecasted: boolean;
}

export interface CompareSummary {
  total_slots: number;
  forecasted_slots: number;
  coverage: number;
  mae: number | null;
  rmse: number | null;
  bias: number | null;
}

export interface CompareResponse {
  delivery_date: string;
  cutoff_hour_utc: number;
  cutoff_time: string;
  forecast_run_publish_time_min: string | null;
  forecast_run_publish_time_max: string | null;
  summary: CompareSummary;
  slots: CompareSlot[];
  assumptions: AssumptionsMeta;
}

export interface MetricsResponse {
  start_date: string;
  end_date: string;
  cutoff_hour_utc: number;
  n_total_slots: number;
  n_forecasted_slots: number;
  coverage: number;
  mae: number | null;
  rmse: number | null;
  bias: number | null;
  p50_abs_error: number | null;
  p90_abs_error: number | null;
  p95_abs_error: number | null;
  p05: number | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  p95: number | null;
  mean_actual_mw: number | null;
  normalized_mae: number | null;
  assumptions: AssumptionsMeta;
}

export interface HorizonBucket {
  bucket: string;
  min_horizon_hours: number;
  max_horizon_hours: number | null;
  n_forecasts: number;
  mae: number | null;
  rmse: number | null;
  bias: number | null;
}

export interface MetricsByHorizonResponse {
  start_date: string;
  end_date: string;
  buckets: HorizonBucket[];
  metadata: {
    timezone: string;
    error_convention: string;
    cutoff_rule: string;
    exclusion_rule: string;
    [key: string]: any;
  };
}

export interface CutoffMetricItem {
  cutoff_hour_utc: number;
  cutoff_label: string;
  // Like-for-like common-set metrics
  common_mae?: number | null;
  common_rmse?: number | null;
  common_bias?: number | null;
  common_p90_abs_error?: number | null;
  n_common_hours?: number;
  // Per-cutoff own-coverage metrics
  mae: number | null;
  rmse: number | null;
  bias: number | null;
  p90_abs_error: number | null;
  coverage: number;
  n_forecasted_slots: number;
  n_total_slots?: number | null;
}

export interface MetricsByCutoffResponse {
  start_date: string;
  end_date: string;
  n_common_hours?: number | null;
  n_total_possible_hours?: number | null;
  by_cutoff: CutoffMetricItem[];
  assumptions: AssumptionsMeta;
}

export interface DailyMetricItem {
  delivery_date: string;
  mean_actual_mw: number | null;
  mean_forecast_mw: number | null;
  bias_mw: number | null;
  mae_mw: number | null;
  coverage: number;
  forecasted_slots: number;
  total_slots: number;
}

export interface MetricsDailyResponse {
  start_date: string;
  end_date: string;
  cutoff_hour_utc: number;
  daily: DailyMetricItem[];
  assumptions: AssumptionsMeta;
}

export interface HourMetric {
  target_hour_utc: number;
  n_slots: number;
  mae: number | null;
  bias: number | null;
  mean_actual_mw: number | null;
  mean_forecast_mw: number | null;
}

export interface MetricsByHourResponse {
  start_date: string;
  end_date: string;
  cutoff_hour_utc: number;
  by_hour: HourMetric[];
  assumptions: AssumptionsMeta;
}

export interface ErrorDistributionBin {
  bin_start: number;
  bin_end: number;
  bin_label: string;
  count: number;
}

export interface ErrorDistributionResponse {
  start_date: string;
  end_date: string;
  cutoff_hour_utc: number;
  bin_width_mw: number;
  total_count: number;
  bins: ErrorDistributionBin[];
  assumptions: AssumptionsMeta;
}
