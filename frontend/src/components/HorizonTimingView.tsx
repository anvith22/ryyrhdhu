import React, { useState, useEffect, useMemo } from 'react';
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
  ReferenceLine,
  ReferenceArea,
} from 'recharts';
import { Clock, TrendingUp, AlertCircle, Sparkles } from 'lucide-react';
import { apiClient } from '../api/client';
import { MetricsByCutoffResponse, MetricsByHorizonResponse } from '../types/api';
import { formatMW } from '../utils/formatters';

/**
 * Assumed UK day-ahead market decision gate closure hour in UTC.
 * Documented as an unverified operational assumption.
 */
export const ASSUMED_GATE_CLOSURE_HOUR_UTC = 9;

interface HorizonTimingViewProps {
  startDate: string;
  endDate: string;
  selectedCutoffHour: number;
}

export const HorizonTimingView: React.FC<HorizonTimingViewProps> = ({
  startDate,
  endDate,
  selectedCutoffHour,
}) => {
  const [horizonData, setHorizonData] = useState<MetricsByHorizonResponse | null>(null);
  const [cutoffData, setCutoffData] = useState<MetricsByCutoffResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      apiClient.getMetricsByHorizon(startDate, endDate),
      apiClient.getMetricsByCutoff(startDate, endDate),
    ])
      .then(([h, c]) => {
        if (!isCancelled) {
          setHorizonData(h);
          setCutoffData(c);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!isCancelled) {
          setError(err.message || 'Failed to load horizon and timing metrics');
          setLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [startDate, endDate]);

  // Compute two plain-language takeaway sentences based on the like-for-like common set
  const takeawaySentences = useMemo(() => {
    if (!cutoffData || cutoffData.by_cutoff.length === 0) return { actionable: '', informational: '' };
    const cutoffMap = new Map(cutoffData.by_cutoff.map((c) => [c.cutoff_hour_utc, c]));
    const c0 = cutoffMap.get(0);
    const cGate = cutoffMap.get(ASSUMED_GATE_CLOSURE_HOUR_UTC);
    const c23 = cutoffMap.get(23);
    const nHours = cutoffData.n_common_hours || c0?.n_common_hours || 682;

    let actionable = '';
    let informational = '';

    const mae0 = c0?.common_mae ?? c0?.mae;
    const maeGate = cGate?.common_mae ?? cGate?.mae;
    const mae23 = c23?.common_mae ?? c23?.mae;

    if (mae0 != null && maeGate != null) {
      const diff0toGate = mae0 - maeGate;
      const pct0toGate = ((diff0toGate / mae0) * 100).toFixed(1);
      actionable = `Within the actionable decision window (D-1 00:00 to assumed gate closure at ${String(ASSUMED_GATE_CLOSURE_HOUR_UTC).padStart(2, '0')}:00 UTC, evaluated on ${nHours} common hours): MAE decreases from ${Math.round(mae0)} MW at 00:00 to ${Math.round(maeGate)} MW at 09:00 (a reduction of ${Math.round(diff0toGate)} MW, or ${pct0toGate}%).`;
    }

    if (maeGate != null && mae23 != null) {
      const diffGateTo23 = maeGate - mae23;
      const pctGateTo23 = ((diffGateTo23 / maeGate) * 100).toFixed(1);
      informational = `Beyond assumed gate closure (informational only, D-1 09:00 to 23:00 UTC, evaluated on ${nHours} common hours): MAE further decreases from ${Math.round(maeGate)} MW at 09:00 to ${Math.round(mae23)} MW at 23:00 (a further reduction of ${Math.round(diffGateTo23)} MW, or ${pctGateTo23}%).`;
    }

    return { actionable, informational };
  }, [cutoffData]);

  return (
    <div>
      {loading && (
        <div className="state-container">
          <div className="spinner" />
          <div style={{ color: 'var(--text-muted)' }}>Evaluating horizon degradation & cutoff timing...</div>
        </div>
      )}

      {error && (
        <div className="error-banner">
          <AlertCircle size={20} />
          <span>{error}</span>
        </div>
      )}

      {!loading && !error && (
        <>
          {/* Dynamic Takeaway Banner with Actionable & Informational Windows */}
          {(takeawaySentences.actionable || takeawaySentences.informational) && (
            <div className="decision-banner" style={{ borderLeftColor: 'var(--accent-indigo)' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
                <Sparkles size={22} color="var(--accent-indigo)" style={{ marginTop: '0.15rem', flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#fff' }}>
                    Decision Timing Takeaways (Like-for-Like on Common Delivery Hours):
                  </div>
                  {takeawaySentences.actionable && (
                    <div style={{ fontSize: '0.85rem', color: 'var(--text-main)', marginTop: '0.25rem' }}>
                      <strong>(a) Actionable Window:</strong> {takeawaySentences.actionable}
                    </div>
                  )}
                  {takeawaySentences.informational && (
                    <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                      <strong>(b) Informational:</strong> {takeawaySentences.informational}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Section 1: Accuracy by Forecast Horizon Bucket */}
          {horizonData && (
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">
                    <Clock size={18} color="var(--accent-cyan)" />
                    Forecast Degradation by Lead Time (Horizon Buckets)
                  </div>
                  <div className="chart-subtitle">
                    Tracking MAE, RMSE, and bias across forecast horizons (Negative retrospective horizons are strictly excluded)
                  </div>
                </div>
                <div>
                  <span className="brand-badge" style={{ borderColor: 'var(--accent-emerald)', color: 'var(--accent-emerald)' }}>
                    72h Max Horizon
                  </span>
                </div>
              </div>

              <div style={{ width: '100%', height: 340 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={horizonData.buckets} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.07)" vertical={false} />
                    <XAxis dataKey="bucket" stroke="var(--text-dim)" fontSize={12} />
                    <YAxis stroke="var(--text-dim)" fontSize={11} tickFormatter={(v) => `${v} MW`} tickLine={false} />
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
                    <Bar dataKey="mae" name="Bucket MAE" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="rmse" name="Bucket RMSE" fill="#6366f1" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="bias" name="Bucket Bias" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Section 2: Accuracy vs. D-1 Cutoff Hour */}
          {cutoffData && (
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">
                    <TrendingUp size={18} color="var(--accent-cyan)" />
                    Cutoff Timing Sensitivity: MAE & Bias Across Decision Hours (D-1 00:00 to 23:00 UTC)
                  </div>
                  <div className="chart-subtitle">
                    Like-for-like comparison evaluated on {cutoffData.n_common_hours || 682} common delivery hours across all cutoffs. Cutoffs 00:00 to 02:00 UTC have 91.7% coverage (hours 22:00 and 23:00 unforecasted due to 73-step payload limit). Cutoffs after {String(ASSUMED_GATE_CLOSURE_HOUR_UTC).padStart(2, '0')}:00 UTC are marked as after assumed gate closure (informational only).
                  </div>
                </div>
              </div>

              <div style={{ width: '100%', height: 350 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={cutoffData.by_cutoff} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.07)" vertical={false} />
                    <XAxis
                      dataKey="cutoff_hour_utc"
                      stroke="var(--text-dim)"
                      fontSize={11}
                      tickFormatter={(h) => {
                        const item = cutoffData.by_cutoff.find((c) => c.cutoff_hour_utc === h);
                        return item && item.coverage < 1.0 ? `${String(h).padStart(2, '0')}:00*` : `${String(h).padStart(2, '0')}:00`;
                      }}
                    />
                    <YAxis stroke="var(--text-dim)" fontSize={11} tickFormatter={(v) => `${v} MW`} tickLine={false} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'rgba(19, 28, 49, 0.95)',
                        borderColor: 'var(--border-subtle)',
                        borderRadius: '8px',
                        color: '#fff',
                        fontSize: '0.8rem',
                        fontFamily: 'var(--font-mono)',
                      }}
                      formatter={(val: any, name: string) => [formatMW(val), name]}
                      labelFormatter={(h) => {
                        const item = cutoffData.by_cutoff.find((c) => c.cutoff_hour_utc === h);
                        const covText = item && item.coverage < 1.0 ? ` — ${(item.coverage * 100).toFixed(1)}% coverage (${item.n_forecasted_slots}h)` : ' — 100% coverage (744h)';
                        return `Decision Cutoff: D-1 ${String(h).padStart(2, '0')}:00 UTC${covText}`;
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: '0.8rem', paddingTop: '10px' }} />
                    <ReferenceArea
                      x1={ASSUMED_GATE_CLOSURE_HOUR_UTC}
                      x2={23}
                      stroke="rgba(245, 158, 11, 0.4)"
                      strokeDasharray="3 3"
                      fill="rgba(245, 158, 11, 0.07)"
                      label={{
                        value: 'After assumed gate closure (informational only)',
                        position: 'insideTopRight',
                        fill: 'var(--accent-amber)',
                        fontSize: 10,
                      }}
                    />
                    <ReferenceLine
                      x={selectedCutoffHour}
                      stroke="var(--accent-cyan)"
                      strokeDasharray="4 4"
                      label={{
                        value: `Selected Cutoff (${String(selectedCutoffHour).padStart(2, '0')}:00)`,
                        position: 'top',
                        fill: 'var(--accent-cyan)',
                        fontSize: 11,
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="common_mae"
                      name={`Common-Set MAE (${cutoffData.n_common_hours || 682}h Like-for-Like)`}
                      stroke="#38bdf8"
                      strokeWidth={2.5}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="mae"
                      name="Own-Set MAE"
                      stroke="#94a3b8"
                      strokeWidth={1.5}
                      strokeDasharray="2 2"
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="common_bias"
                      name="Common-Set Bias"
                      stroke="#f59e0b"
                      strokeWidth={2}
                      strokeDasharray="3 3"
                      dot={{ r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.5rem', textAlign: 'right' }}>
                *Cutoffs marked with an asterisk have &lt;100% coverage (hours 22:00 and 23:00 unforecasted due to 73-step payload limit).
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
