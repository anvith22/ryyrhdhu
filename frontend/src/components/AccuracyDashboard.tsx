import React, { useState, useEffect } from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from 'recharts';
import {
  Calendar,
  Clock,
  AlertCircle,
  TrendingUp,
  Info,
  Layers,
  BarChart2,
} from 'lucide-react';
import { apiClient } from '../api/client';
import {
  ErrorDistributionResponse,
  MetricsByHourResponse,
  MetricsDailyResponse,
  MetricsResponse,
} from '../types/api';
import { formatMW, formatPercent, formatSignedMW } from '../utils/formatters';

interface AccuracyDashboardProps {
  startDate: string;
  setStartDate: (d: string) => void;
  endDate: string;
  setEndDate: (d: string) => void;
  cutoffHour: number;
  setCutoffHour: (h: number) => void;
  onOpenMethodology: () => void;
}

export const AccuracyDashboard: React.FC<AccuracyDashboardProps> = ({
  startDate,
  setStartDate,
  endDate,
  setEndDate,
  cutoffHour,
  setCutoffHour,
  onOpenMethodology,
}) => {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [dailyMetrics, setDailyMetrics] = useState<MetricsDailyResponse | null>(null);
  const [hourMetrics, setHourMetrics] = useState<MetricsByHourResponse | null>(null);
  const [errorDist, setErrorDist] = useState<ErrorDistributionResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      apiClient.getMetrics(startDate, endDate, cutoffHour),
      apiClient.getMetricsDaily(startDate, endDate, cutoffHour),
      apiClient.getMetricsByHour(startDate, endDate, cutoffHour),
      apiClient.getErrorDistribution(startDate, endDate, cutoffHour),
    ])
      .then(([m, d, h, e]) => {
        if (!isCancelled) {
          setMetrics(m);
          setDailyMetrics(d);
          setHourMetrics(h);
          setErrorDist(e);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!isCancelled) {
          setError(err.message || 'Failed to load accuracy metrics');
          setLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [startDate, endDate, cutoffHour]);

  return (
    <div>
      {/* Controls */}
      <div className="control-bar">
        <div className="control-group">
          <Calendar size={18} color="var(--accent-cyan)" />
          <span className="control-label">Evaluation Range:</span>
          <input
            type="date"
            className="input-date"
            min="2026-01-01"
            max="2026-01-31"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
          <span style={{ color: 'var(--text-dim)' }}>to</span>
          <input
            type="date"
            className="input-date"
            min="2026-01-01"
            max="2026-01-31"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>

        <div className="control-group">
          <Clock size={18} color="var(--accent-cyan)" />
          <span className="control-label">D-1 Cutoff:</span>
          <select
            className="input-select"
            value={cutoffHour}
            onChange={(e) => setCutoffHour(Number(e.target.value))}
          >
            {Array.from({ length: 24 }).map((_, i) => (
              <option key={i} value={i}>
                D-1 {String(i).padStart(2, '0')}:00 UTC {i === 9 ? '(Default)' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && (
        <div className="state-container">
          <div className="spinner" />
          <div style={{ color: 'var(--text-muted)' }}>Computing backtest accuracy metrics...</div>
        </div>
      )}

      {error && (
        <div className="error-banner">
          <AlertCircle size={20} />
          <span>{error}</span>
        </div>
      )}

      {!loading && !error && metrics && (
        <>
          {/* Key Metric Cards */}
          <div className="kpi-grid">
            {/* Coverage */}
            <div className="kpi-card" title="Proportion of target delivery hours that had an eligible forecast prior to cutoff.">
              <div className="kpi-header">
                <span className="kpi-title">Coverage</span>
                <Layers size={14} color="var(--text-dim)" />
              </div>
              <div className="kpi-value">{formatPercent(metrics.coverage)}</div>
              <div className="kpi-subtext">
                {metrics.n_forecasted_slots} of {metrics.n_total_slots} hours forecasted
              </div>
            </div>

            {/* MAE */}
            <div className="kpi-card" title="Mean Absolute Error: Average magnitude of forecast error regardless of direction.">
              <div className="kpi-header">
                <span className="kpi-title">Mean Absolute Error (MAE)</span>
              </div>
              <div className="kpi-value">{formatMW(metrics.mae)}</div>
              <div className="kpi-subtext">Normalized: {formatPercent(metrics.normalized_mae)} of actual</div>
            </div>

            {/* RMSE */}
            <div className="kpi-card" title="Root Mean Squared Error: Penalizes larger forecast errors more heavily.">
              <div className="kpi-header">
                <span className="kpi-title">RMSE</span>
              </div>
              <div className="kpi-value">{formatMW(metrics.rmse)}</div>
              <div className="kpi-subtext">Std error of forecast deviation</div>
            </div>

            {/* Bias */}
            <div
              className="kpi-card"
              title="Mean Error (Forecast - Actual). Positive bias means buyer under-buys power day-ahead and is left short in real-time."
            >
              <div className="kpi-header">
                <span className="kpi-title">Bias (Mean Error)</span>
                <button
                  onClick={onOpenMethodology}
                  style={{ background: 'none', border: 'none', color: 'var(--accent-amber)', cursor: 'pointer' }}
                  title="View scope note regarding embedded wind"
                >
                  <Info size={15} />
                </button>
              </div>
              <div className={`kpi-value ${metrics.bias && metrics.bias > 0 ? 'kpi-bias-positive' : 'kpi-bias-negative'}`}>
                {formatSignedMW(metrics.bias)}
              </div>
              <div className="kpi-subtext" style={{ color: 'var(--accent-amber)' }}>
                Over-forecast: buyer short in real-time
              </div>
            </div>

            {/* P90 Abs Error */}
            <div className="kpi-card" title="90% of hourly forecast errors were smaller than this magnitude.">
              <div className="kpi-header">
                <span className="kpi-title">P90 Absolute Error</span>
              </div>
              <div className="kpi-value">{formatMW(metrics.p90_abs_error)}</div>
              <div className="kpi-subtext">P50: {formatMW(metrics.p50_abs_error)} | P95: {formatMW(metrics.p95_abs_error)}</div>
            </div>

            {/* Normalized MAE */}
            <div className="kpi-card" title="Normalized MAE = MAE / mean_actual. Expresses relative error scale without MAPE singularity.">
              <div className="kpi-header">
                <span className="kpi-title">Normalized MAE</span>
              </div>
              <div className="kpi-value">{formatPercent(metrics.normalized_mae)}</div>
              <div className="kpi-subtext">Mean actual: {formatMW(metrics.mean_actual_mw)}</div>
            </div>
          </div>

          {/* Chart 1: Daily Bias and MAE over the Month */}
          {dailyMetrics && (
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">
                    <TrendingUp size={18} color="var(--accent-cyan)" />
                    Daily Forecast Accuracy & Bias Across Month
                  </div>
                  <div className="chart-subtitle">
                    Tracking daily MAE and net signed bias (Forecast - Actual) per day. Forecast/actual ratio falls between 1.07 and 1.35 on 22 of 31 days (min: 0.89, max: 1.93, median: 1.14).
                  </div>
                </div>
              </div>

              <div style={{ width: '100%', height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={dailyMetrics.daily} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.07)" vertical={false} />
                    <XAxis
                      dataKey="delivery_date"
                      stroke="var(--text-dim)"
                      fontSize={11}
                      tickFormatter={(d) => d.slice(8)}
                      interval={1}
                    />
                    <YAxis
                      stroke="var(--text-dim)"
                      fontSize={11}
                      tickFormatter={(v) => `${v} MW`}
                      tickLine={false}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'rgba(19, 28, 49, 0.95)',
                        borderColor: 'var(--border-subtle)',
                        borderRadius: '8px',
                        color: '#fff',
                        fontSize: '0.8rem',
                        fontFamily: 'var(--font-mono)',
                      }}
                      formatter={(val: any) => [formatMW(val), '']}
                    />
                    <Legend wrapperStyle={{ fontSize: '0.8rem', paddingTop: '10px' }} />
                    <Bar dataKey="mae_mw" name="Daily MAE" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="bias_mw" name="Daily Bias" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Chart 2: Signed Error Distribution (Histogram) */}
          {errorDist && (
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">
                    <BarChart2 size={18} color="var(--accent-cyan)" />
                    Signed Error Distribution (500 MW Histogram Bins)
                  </div>
                  <div className="chart-subtitle">
                    Distribution of forecast error (Forecast - Actual). Positive values represent over-forecasting.
                  </div>
                </div>
              </div>

              <div style={{ width: '100%', height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={errorDist.bins} margin={{ top: 10, right: 20, left: 10, bottom: 40 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.07)" vertical={false} />
                    <XAxis
                      dataKey="bin_label"
                      stroke="var(--text-dim)"
                      fontSize={10}
                      angle={-45}
                      textAnchor="end"
                      interval={1}
                    />
                    <YAxis
                      stroke="var(--text-dim)"
                      fontSize={11}
                      tickLine={false}
                      label={{ value: 'Hours', angle: -90, position: 'insideLeft', fill: 'var(--text-dim)' }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'rgba(19, 28, 49, 0.95)',
                        borderColor: 'var(--border-subtle)',
                        borderRadius: '8px',
                        color: '#fff',
                        fontSize: '0.8rem',
                        fontFamily: 'var(--font-mono)',
                      }}
                      formatter={(val: any) => [`${val} hours`, 'Count']}
                    />
                    <Bar dataKey="count" name="Hours in Bin" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Chart 3: MAE and Bias by Hour of Day */}
          {hourMetrics && (
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">
                    <Clock size={18} color="var(--accent-cyan)" />
                    Forecast Accuracy by Target Delivery Hour (00:00 to 23:00 UTC)
                  </div>
                  <div className="chart-subtitle">
                    Diurnal profile of MAE and bias across the 24 hourly settlement hours
                  </div>
                </div>
              </div>

              <div style={{ width: '100%', height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={hourMetrics.by_hour} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.07)" vertical={false} />
                    <XAxis
                      dataKey="target_hour_utc"
                      stroke="var(--text-dim)"
                      fontSize={11}
                      tickFormatter={(h) => `${String(h).padStart(2, '0')}:00`}
                    />
                    <YAxis
                      stroke="var(--text-dim)"
                      fontSize={11}
                      tickFormatter={(v) => `${v} MW`}
                      tickLine={false}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'rgba(19, 28, 49, 0.95)',
                        borderColor: 'var(--border-subtle)',
                        borderRadius: '8px',
                        color: '#fff',
                        fontSize: '0.8rem',
                        fontFamily: 'var(--font-mono)',
                      }}
                      formatter={(val: any) => [formatMW(val), '']}
                      labelFormatter={(h) => `Target Hour: ${String(h).padStart(2, '0')}:00 UTC`}
                    />
                    <Legend wrapperStyle={{ fontSize: '0.8rem', paddingTop: '10px' }} />
                    <Line type="monotone" dataKey="mae" name="Hour MAE" stroke="#38bdf8" strokeWidth={2.5} dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="bias" name="Hour Bias" stroke="#f59e0b" strokeWidth={2} strokeDasharray="3 3" dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
