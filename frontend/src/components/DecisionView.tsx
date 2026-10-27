import React, { useState, useEffect } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import {
  Calendar,
  Clock,
  Download,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  FileSpreadsheet,
  TrendingUp,
  Info,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { CompareResponse, MetricsResponse } from '../types/api';
import { calculatePlausibleBand } from '../utils/calculations';
import {
  formatMW,
  formatMWh,
  formatSignedMW,
  formatTimeUTC,
  formatDateTimeUTC,
  exportSlotsToCSV,
} from '../utils/formatters';

interface DecisionViewProps {
  deliveryDate: string;
  setDeliveryDate: (d: string) => void;
  cutoffHour: number;
  setCutoffHour: (h: number) => void;
  onOpenMethodology: () => void;
}

export const DecisionView: React.FC<DecisionViewProps> = ({
  deliveryDate,
  setDeliveryDate,
  cutoffHour,
  setCutoffHour,
  onOpenMethodology,
}) => {
  const [compareData, setCompareData] = useState<CompareResponse | null>(null);
  const [metricsData, setMetricsData] = useState<MetricsResponse | null>(null);
  const [actuals30Min, setActuals30Min] = useState<{ start_time: string; generation_mw: number }[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isTableExpanded, setIsTableExpanded] = useState<boolean>(false);

  useEffect(() => {
    let isCancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      apiClient.getCompare(deliveryDate, cutoffHour),
      apiClient.getActuals(deliveryDate, deliveryDate),
      apiClient.getMetrics('2026-01-01', '2026-01-31', cutoffHour),
    ])
      .then(([cmp, act, met]) => {
        if (!isCancelled) {
          setCompareData(cmp);
          setActuals30Min(act.items);
          setMetricsData(met);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!isCancelled) {
          setError(err.message || 'Failed to load decision data');
          setLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [deliveryDate, cutoffHour]);

  // Combine 30-min actuals with hourly forecasts into aligned chart points
  const q10 = metricsData?.p10 ?? 0;
  const q90 = metricsData?.p90 ?? 0;

  const chartData = React.useMemo(() => {
    if (!compareData) return [];

    // Map hourly forecasts by ISO start_time
    const forecastMap = new Map(compareData.slots.map((s) => [s.start_time, s]));

    // Use all 48 half-hour slots for the day
    return actuals30Min.map((act) => {
      const dt = new Date(act.start_time);
      const isTopHour = dt.getUTCMinutes() === 0;

      // Find forecast associated with the top of the hour
      const hourDate = new Date(dt);
      hourDate.setUTCMinutes(0, 0, 0);
      const hourIso = hourDate.toISOString().replace('.000Z', 'Z');
      const fcSlot = forecastMap.get(hourIso);

      const forecastMw = fcSlot?.forecast_mw ?? null;
      const band = calculatePlausibleBand(forecastMw, q10, q90);

      return {
        time_iso: act.start_time,
        time_label: formatTimeUTC(act.start_time),
        actual_mw_30m: act.generation_mw,
        forecast_mw: forecastMw,
        plausible_lower: band.lower,
        plausible_band: band.bandHeight, // height for stacked area
        plausible_upper: band.upper,
        publish_time: fcSlot?.publish_time,
        horizon_hours: fcSlot?.horizon_hours,
        is_top_hour: isTopHour,
      };
    });
  }, [actuals30Min, compareData, q10, q90]);

  // Compute banner metrics
  const minPublish = compareData?.forecast_run_publish_time_min;
  const maxPublish = compareData?.forecast_run_publish_time_max;
  const cutoffIso = compareData?.cutoff_time;

  let leadTimeBeforeCutoff = '';
  if (cutoffIso && maxPublish) {
    const cutoffMs = new Date(cutoffIso).getTime();
    const pubMs = new Date(maxPublish).getTime();
    const diffHours = (cutoffMs - pubMs) / (1000 * 3600);
    leadTimeBeforeCutoff = `${diffHours.toFixed(1)}h before cutoff`;
  }

  // Summary figures
  const meanActual = compareData?.slots.reduce((acc, s) => acc + (s.actual_mw || 0), 0)! / 24;
  const meanForecast = compareData?.slots.reduce((acc, s) => acc + (s.forecast_mw || 0), 0)! / 24;
  const totalActualMWh = meanActual * 24;
  const totalForecastMWh = meanForecast * 24;

  return (
    <div>
      {/* Controls */}
      <div className="control-bar">
        <div className="control-group">
          <Calendar size={18} color="var(--accent-cyan)" />
          <span className="control-label">Delivery Date:</span>
          <input
            type="date"
            className="input-date"
            min="2026-01-01"
            max="2026-01-31"
            value={deliveryDate}
            onChange={(e) => setDeliveryDate(e.target.value)}
          />
        </div>

        <div className="control-group">
          <Clock size={18} color="var(--accent-cyan)" />
          <span className="control-label">D-1 Decision Cutoff:</span>
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

      {/* Prominent Banner */}
      {compareData && (
        <div className="decision-banner">
          <div>
            <div className="banner-text-primary">
              <Clock size={16} color="var(--accent-cyan)" />
              Latest Forecast Available at Decision Cutoff ({formatDateTimeUTC(cutoffIso)})
            </div>
            <div className="banner-text-secondary">
              Published run:{' '}
              {minPublish === maxPublish
                ? formatDateTimeUTC(maxPublish)
                : `${formatDateTimeUTC(minPublish)} to ${formatDateTimeUTC(maxPublish)}`}{' '}
              {leadTimeBeforeCutoff && `(${leadTimeBeforeCutoff})`}
            </div>
          </div>
          <div>
            <span className="brand-badge" style={{ fontSize: '0.75rem', borderColor: 'var(--accent-cyan)' }}>
              Evaluation: Hourly Aligned
            </span>
          </div>
        </div>
      )}

      {/* Loading & Error States */}
      {loading && (
        <div className="state-container">
          <div className="spinner" />
          <div style={{ color: 'var(--text-muted)' }}>Loading decision market data...</div>
        </div>
      )}

      {error && (
        <div className="error-banner">
          <AlertCircle size={20} />
          <span>{error}</span>
        </div>
      )}

      {!loading && !error && compareData && (
        <>
          {/* Day KPI Summary Cards */}
          <div className="kpi-grid">
            <div className="kpi-card">
              <div className="kpi-header">
                <span className="kpi-title">Forecast Energy</span>
              </div>
              <div className="kpi-value">{formatMW(meanForecast)}</div>
              <div className="kpi-subtext">Total: {formatMWh(totalForecastMWh)}</div>
            </div>

            <div className="kpi-card">
              <div className="kpi-header">
                <span className="kpi-title">Actual Energy</span>
              </div>
              <div className="kpi-value">{formatMW(meanActual)}</div>
              <div className="kpi-subtext">Total: {formatMWh(totalActualMWh)}</div>
            </div>

            <div className="kpi-card">
              <div className="kpi-header">
                <span className="kpi-title">Day Bias (Forecast - Actual)</span>
                <button
                  onClick={onOpenMethodology}
                  title="View scope note"
                  style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}
                >
                  <Info size={14} />
                </button>
              </div>
              <div className={`kpi-value ${compareData.summary.bias && compareData.summary.bias > 0 ? 'kpi-bias-positive' : 'kpi-bias-negative'}`}>
                {formatSignedMW(compareData.summary.bias)}
              </div>
              <div className="kpi-subtext">
                {compareData.summary.bias && compareData.summary.bias > 0
                  ? 'Over-forecast (buyer short in balancing)'
                  : 'Under-forecast (buyer long)'}
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-header">
                <span className="kpi-title">Day Mean Absolute Error</span>
              </div>
              <div className="kpi-value">{formatMW(compareData.summary.mae)}</div>
              <div className="kpi-subtext">RMSE: {formatMW(compareData.summary.rmse)}</div>
            </div>
          </div>

          {/* Main Chart */}
          <div className="chart-card">
            <div className="chart-header">
              <div>
                <div className="chart-title">
                  <TrendingUp size={18} color="var(--accent-cyan)" />
                  Wind Generation Profile: Actual vs. Decision Forecast ({deliveryDate})
                </div>
                <div className="chart-subtitle">
                  Showing 30-min actual line, hourly step forecast, and backtest P10-P90 plausible actual band
                </div>
              </div>

              <div className="chart-legend-custom">
                <div className="legend-item">
                  <span className="legend-dot" style={{ backgroundColor: '#0284c7' }} />
                  Actual (30-min FUELHH)
                </div>
                <div className="legend-item">
                  <span className="legend-dot" style={{ backgroundColor: '#f43f5e' }} />
                  Forecast at Cutoff (WINDFOR)
                </div>
                <div className="legend-item">
                  <span className="legend-dot" style={{ backgroundColor: 'rgba(56, 189, 248, 0.25)' }} />
                  Plausible Actual Band (P10–P90 in-sample)
                </div>
              </div>
            </div>

            <div style={{ width: '100%', height: 420 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.07)" vertical={false} />
                  <XAxis
                    dataKey="time_label"
                    stroke="var(--text-dim)"
                    fontSize={11}
                    tickLine={false}
                    interval={3}
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
                    formatter={(val: any, name: string) => {
                      if (name === 'plausible_band') return [null, null];
                      if (name === 'plausible_lower') return [null, null];
                      return [formatMW(val), name];
                    }}
                    labelFormatter={(label, items) => {
                      const item = items?.[0]?.payload;
                      return `${label} ${item?.publish_time ? `(Pub: ${formatTimeUTC(item.publish_time)})` : ''}`;
                    }}
                  />

                  {/* Shaded Area for P10-P90 Quantile Band (Stacked transparent base + height) */}
                  <Area
                    type="stepAfter"
                    dataKey="plausible_lower"
                    stackId="band"
                    stroke="none"
                    fill="transparent"
                  />
                  <Area
                    type="stepAfter"
                    name="Plausible Band (P10-P90)"
                    dataKey="plausible_band"
                    stackId="band"
                    stroke="rgba(56, 189, 248, 0.4)"
                    strokeDasharray="2 2"
                    fill="rgba(56, 189, 248, 0.15)"
                  />

                  {/* Hourly Step Forecast Line */}
                  <Line
                    type="stepAfter"
                    name="Forecast MW"
                    dataKey="forecast_mw"
                    stroke="#f43f5e"
                    strokeWidth={2.5}
                    dot={{ r: 3, fill: '#f43f5e' }}
                  />

                  {/* 30-Minute Actual Generation Line */}
                  <Line
                    type="monotone"
                    name="Actual MW (30m)"
                    dataKey="actual_mw_30m"
                    stroke="#38bdf8"
                    strokeWidth={2}
                    dot={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Collapsible Hourly Data Table */}
          <div className="table-card">
            <div className="table-header" onClick={() => setIsTableExpanded(!isTableExpanded)}>
              <div className="table-title">
                <FileSpreadsheet size={18} color="var(--accent-cyan)" />
                Hourly Comparison Data Table ({compareData.slots.length} Hours)
              </div>
              <div className="table-actions">
                <button
                  className="btn-secondary"
                  onClick={(e) => {
                    e.stopPropagation();
                    exportSlotsToCSV(compareData.slots, deliveryDate);
                  }}
                >
                  <Download size={14} />
                  Export CSV
                </button>
                {isTableExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
              </div>
            </div>

            {isTableExpanded && (
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Hour (UTC)</th>
                      <th>Actual MW (Hourly Mean)</th>
                      <th>Forecast MW</th>
                      <th>Error MW (Fc - Act)</th>
                      <th>Abs Error</th>
                      <th>Publish Time</th>
                      <th>Horizon</th>
                    </tr>
                  </thead>
                  <tbody>
                    {compareData.slots.map((s) => (
                      <tr key={s.start_time}>
                        <td>{formatTimeUTC(s.start_time)}</td>
                        <td>{formatMW(s.actual_mw)}</td>
                        <td>{formatMW(s.forecast_mw)}</td>
                        <td style={{ color: s.error_mw && s.error_mw > 0 ? 'var(--accent-amber)' : 'var(--accent-cyan)' }}>
                          {formatSignedMW(s.error_mw)}
                        </td>
                        <td>{formatMW(s.abs_error_mw)}</td>
                        <td>{formatDateTimeUTC(s.publish_time)}</td>
                        <td>{s.horizon_hours !== null ? `${s.horizon_hours.toFixed(1)}h` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};
