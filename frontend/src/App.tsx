import React, { useState } from 'react';
import { Navbar, TabKey } from './components/Navbar';
import { DecisionView } from './components/DecisionView';
import { AccuracyDashboard } from './components/AccuracyDashboard';
import { HorizonTimingView } from './components/HorizonTimingView';
import { MethodologyModal } from './components/MethodologyModal';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabKey>('decision');
  const [deliveryDate, setDeliveryDate] = useState<string>('2026-01-15');
  const [startDate, setStartDate] = useState<string>('2026-01-01');
  const [endDate, setEndDate] = useState<string>('2026-01-31');
  const [cutoffHour, setCutoffHour] = useState<number>(9);
  const [isMethodologyOpen, setIsMethodologyOpen] = useState<boolean>(false);

  return (
    <div className="app-container">
      <Navbar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        onOpenMethodology={() => setIsMethodologyOpen(true)}
      />

      <main className="main-content">
        {activeTab === 'decision' && (
          <DecisionView
            deliveryDate={deliveryDate}
            setDeliveryDate={setDeliveryDate}
            cutoffHour={cutoffHour}
            setCutoffHour={setCutoffHour}
            onOpenMethodology={() => setIsMethodologyOpen(true)}
          />
        )}

        {activeTab === 'accuracy' && (
          <AccuracyDashboard
            startDate={startDate}
            setStartDate={setStartDate}
            endDate={endDate}
            setEndDate={setEndDate}
            cutoffHour={cutoffHour}
            setCutoffHour={setCutoffHour}
            onOpenMethodology={() => setIsMethodologyOpen(true)}
          />
        )}

        {activeTab === 'horizon' && (
          <HorizonTimingView
            startDate={startDate}
            endDate={endDate}
            selectedCutoffHour={cutoffHour}
          />
        )}
      </main>

      <MethodologyModal
        isOpen={isMethodologyOpen}
        onClose={() => setIsMethodologyOpen(false)}
      />
    </div>
  );
};

export default App;
