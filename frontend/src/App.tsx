import { useState } from 'react';
import { BackendStatus } from './components/BackendStatus';
import { ErrorPanel } from './components/ErrorPanel';
import { MissionControls } from './components/MissionControls';
import { ScientificResults } from './components/ScientificResults';
import { useLunarAnalysis } from './hooks/useLunarAnalysis';
import { initialSimulation, type SimulationState } from './state/simulation';

export default function App() {
  const [simulation, setSimulation] = useState<SimulationState>(initialSimulation);
  const [attempted, setAttempted] = useState(false);
  const state = useLunarAnalysis();
  const run = () => { setAttempted(true); void state.analyze(simulation); };
  return <div className="app-shell"><header className="masthead"><div className="identity"><div className="moon-mark" aria-hidden="true">◐</div><div><p className="eyebrow">NASA SPACE APPS CHALLENGE 2026 · TEAM LUNASOLUM</p><h1>Lunasolum <span>/ Mission Control</span></h1><p className="tagline">Scientific lunar landing-site navigator</p></div></div><div className="header-label">LUNAR SCIENCE · API v1</div></header>
    <main className="dashboard"><aside className="sidebar"><MissionControls value={simulation} onChange={setSimulation} onAnalyze={run} busy={state.loading} /><BackendStatus health={state.health} checking={state.checking} onRetry={() => void state.checkConnection()} />{state.inputError && <ErrorPanel title="Invalid mission controls" message={state.inputError} />}</aside><ScientificResults geometry={state.geometry} analysis={state.analysis} metadata={state.metadata} busy={state.loading} attempted={attempted} backendOffline={Boolean(state.health.error)} /></main>
    <footer>Science computed by FastAPI / lunar_engine. Visual presentation does not calculate astronomical geometry.</footer></div>;
}
