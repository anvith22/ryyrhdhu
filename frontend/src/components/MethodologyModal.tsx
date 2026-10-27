import React from 'react';
import { X, BookOpen, AlertTriangle, Layers, Calendar, Compass, ShieldAlert } from 'lucide-react';

interface MethodologyModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const MethodologyModal: React.FC<MethodologyModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <BookOpen size={20} color="var(--accent-cyan)" />
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff' }}>
              Data Sources, Methodology & Trading Assumptions
            </h3>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '0.25rem',
            }}
          >
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          {/* Important Scope Caveat */}
          <div className="caveat-box">
            <div className="caveat-header">
              <ShieldAlert size={18} />
              CRITICAL SCOPE CAVEAT: FUELHH VS. WINDFOR DEFINITIONS
            </div>
            <div className="caveat-body">
              <p style={{ margin: '0 0 0.5rem 0' }}>
                The observed positive forecast bias is persistent across horizons and days. This may partly reflect scope differences between datasets and partly forecast error; the available public stream data cannot separate the two.
              </p>
              <ul style={{ paddingLeft: '1.25rem', margin: '0.4rem 0' }}>
                <li>
                  <strong>FUELHH Actuals:</strong> Elexon's official documentation notes that FUELHH originates from operational metering for BMUs connected directly to the transmission system: <em>"Renewable generation figures can be underestimated because the dataset excludes embedded generation and wind farms that lack operational meters."</em>
                </li>
                <li>
                  <strong>WINDFOR Forecasts:</strong> Defined by Elexon as <em>"A forecast of generation output for all Power Park Modules (PPMs) connected to the system."</em>
                </li>
              </ul>
              <p style={{ margin: '0.5rem 0 0 0' }}>
                However, the daily forecast/actual ratio varies widely across the month (between 1.07 and 1.35 on 22 of 31 days, with an overall range of 0.89 to 1.93 and a median of 1.14). Because of this wide day-to-day variation, a constant-scope explanation alone is not supported. We state only the computed data and do not assert a definitive cause.
              </p>
            </div>
          </div>

          <div style={{ height: '1.25rem' }} />

          {/* Core Assumptions */}
          <div className="modal-section">
            <div className="modal-section-title">
              <Calendar size={16} />
              1. Day-Ahead Decision Cutoff Rule
            </div>
            <div className="modal-text">
              Electricity buyers commit volume purchases on the UK day-ahead auction on day <strong>D-1</strong>. By default, the decision cutoff is assumed to be <strong>09:00 UTC</strong> on D-1. The platform strictly filters available forecasts such that for any target delivery slot:
              <div style={{ margin: '0.5rem 0', padding: '0.4rem 0.75rem', background: 'rgba(0,0,0,0.3)', borderRadius: '6px', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                publish_time &le; cutoff_timestamp (D-1 at cutoff_hour:00 UTC)
              </div>
              Any forecast published after the cutoff is future information unavailable at procurement time and is excluded.
            </div>
          </div>

          <div className="modal-section">
            <div className="modal-section-title">
              <Layers size={16} />
              2. Hourly Resolution Alignment
            </div>
            <div className="modal-text">
              <code>WINDFOR</code> forecasts are published at hourly intervals (73 hourly steps from 0h to 72h ahead), whereas <code>FUELHH</code> actuals are settled at half-hour intervals. In all evaluations and metrics:
              <ul style={{ paddingLeft: '1.25rem', marginTop: '0.4rem' }}>
                <li>A forecast for <code>startTime T</code> is assumed to cover the full 1-hour block <code>[T, T + 1h)</code>.</li>
                <li>The hourly actual is computed as the arithmetic mean of the two half-hour actuals in that hour.</li>
                <li>Unforecasted hours denote that no forecast run was published before the decision cutoff.</li>
              </ul>
            </div>
          </div>

          <div className="modal-section">
            <div className="modal-section-title">
              <Compass size={16} />
              3. Error Sign Convention & Commercial Impact
            </div>
            <div className="modal-text">
              Forecast error is defined uniformly as:
              <div style={{ margin: '0.5rem 0', padding: '0.4rem 0.75rem', background: 'rgba(0,0,0,0.3)', borderRadius: '6px', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                Error = Forecast - Actual &nbsp;&nbsp;|&nbsp;&nbsp; Abs_Error = |Forecast - Actual|
              </div>
              <strong>Commercial Interpretation:</strong> A positive error (over-forecast) means the trading desk expected more wind energy than was actually generated. As a result, the buyer under-procured day-ahead wholesale electricity, leaving them <strong>short</strong> in real-time delivery and exposed to system cash-out balancing mechanism costs.
            </div>
          </div>

          <div className="modal-section">
            <div className="modal-section-title">
              <AlertTriangle size={16} />
              4. Exclusion of Retrospective Forecasts
            </div>
            <div className="modal-text">
              In WINDFOR stream publications, roughly 20% of records have <code>publish_time &gt; start_time</code> (negative forecast horizon, where ESO payloads start earlier than the run time). These retrospective outturn records are strictly excluded from all forward horizon accuracy evaluations.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
