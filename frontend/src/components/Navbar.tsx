import React from 'react';
import { Wind, BarChart3, Clock, LineChart, HelpCircle } from 'lucide-react';

export type TabKey = 'decision' | 'accuracy' | 'horizon';

interface NavbarProps {
  activeTab: TabKey;
  onSelectTab: (tab: TabKey) => void;
  onOpenMethodology: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ activeTab, onSelectTab, onOpenMethodology }) => {
  return (
    <header className="navbar">
      <div className="navbar-inner">
        <div className="brand-section">
          <div className="brand-icon">
            <Wind size={20} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className="brand-title">UK Wind Forecast Desk</span>
              <span className="brand-badge">Day-Ahead</span>
            </div>
            <div style={{ fontSize: '0.725rem', color: 'var(--text-dim)' }}>
              Elexon BMRS Market Operations (All Times UTC)
            </div>
          </div>
        </div>

        <nav className="nav-tabs">
          <button
            className={`tab-btn ${activeTab === 'decision' ? 'active' : ''}`}
            onClick={() => onSelectTab('decision')}
          >
            <LineChart size={16} />
            Decision View
          </button>
          <button
            className={`tab-btn ${activeTab === 'accuracy' ? 'active' : ''}`}
            onClick={() => onSelectTab('accuracy')}
          >
            <BarChart3 size={16} />
            Accuracy Dashboard
          </button>
          <button
            className={`tab-btn ${activeTab === 'horizon' ? 'active' : ''}`}
            onClick={() => onSelectTab('horizon')}
          >
            <Clock size={16} />
            Horizon & Timing
          </button>
        </nav>

        <div>
          <button className="methodology-btn" onClick={onOpenMethodology}>
            <HelpCircle size={15} />
            About Data & Methodology
          </button>
        </div>
      </div>
    </header>
  );
};
