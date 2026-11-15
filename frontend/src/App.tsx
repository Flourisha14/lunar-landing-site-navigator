import { lazy, Suspense, useState } from 'react';
import { BackendStatus } from './components/BackendStatus';
import { ErrorPanel } from './components/ErrorPanel';
import { MissionControls } from './components/MissionControls';
import { LunarGlobe } from './components/LunarGlobe';
import { LunarRecommendations } from './components/LunarRecommendations';
import type { RecommendSitesResponse } from './recommendations/types';
import { normalizeLunarSite } from './globe/lunarCoordinates';
import { ScientificResults } from './components/ScientificResults';
import { useLunarAnalysis } from './hooks/useLunarAnalysis';
import { initialSimulation, type SimulationState } from './state/simulation';
import { buildRequests } from './utils/validation';

const LocalLunarSurface = lazy(() => import('./components/LocalLunarSurface').then(module => ({ default: module.LocalLunarSurface })));

export default function App() {
  const [simulation, setSimulation] = useState<SimulationState>(initialSimulation);
  const [attempted, setAttempted] = useState(false);
  const [localView, setLocalView] = useState(false);
  const [recommendations, setRecommendations] = useState<RecommendSitesResponse | null>(null);
  const [recommendationFocus, setRecommendationFocus] = useState<{ latitudeDeg: number; longitudeDeg: number } | null>(null);
  const state = useLunarAnalysis();
  const run = () => { setAttempted(true); void state.analyze(simulation); };
  const updateControls = (next: SimulationState) => {
    setSimulation(next);
    if (next.dateUTC !== simulation.dateUTC || next.timeUTC !== simulation.timeUTC) {
      setAttempted(true);
      void state.analyze(next);
    }
  };
  let timestampUTC: string | null = null;
  try { timestampUTC = buildRequests(simulation).geometry.timestamp_utc; } catch { /* Invalid input: no scientific light. */ }
  const selectSite = (site: { latitudeDeg: number; longitudeDeg: number }) => {
    const next = { ...simulation, latitude: String(site.latitudeDeg), longitude: String(site.longitudeDeg) };
    setSimulation(next);
    setAttempted(true);
    void state.analyze(next);
  };
  const selectRecommendation = (site: { latitudeDeg: number; longitudeDeg: number }) => { selectSite(site); setRecommendationFocus({ ...site }); };
  return <div className="app-shell"><header className="masthead"><div className="identity"><div className="moon-mark" aria-hidden="true">◐</div><div><p className="eyebrow">NASA SPACE APPS CHALLENGE 2026 · TEAM LUNASOLUM</p><h1>Lunasolum <span>/ Mission Control</span></h1><p className="tagline">Scientific lunar landing-site navigator</p></div></div><div className="header-label">LUNAR SCIENCE · API v1</div></header>
    <main className="dashboard"><aside className="sidebar"><MissionControls value={simulation} onChange={updateControls} onAnalyze={run} busy={state.loading} /><BackendStatus health={state.health} checking={state.checking} onRetry={() => void state.checkConnection()} />{state.inputError && <ErrorPanel title="Invalid mission controls" message={state.inputError} />}</aside><div className="results-column"><div className="view-switcher" role="group" aria-label="Lunar visualization mode"><button type="button" aria-pressed={!localView} onClick={() => setLocalView(false)}>Global Moon · Cesium</button><button type="button" aria-pressed={localView} onClick={() => setLocalView(true)}>Local surface · Babylon</button></div>{localView ? <Suspense fallback={<section className="panel">Loading local surface viewer...</section>}><LocalLunarSurface latitude={simulation.latitude} longitude={simulation.longitude} timestampUTC={timestampUTC} geometry={state.geometry} loading={state.loading} /></Suspense> : <LunarGlobe latitude={simulation.latitude} longitude={simulation.longitude} onSelect={selectSite} candidates={recommendations?.candidates ?? []} onCandidateSelect={selectRecommendation} focusRequest={recommendationFocus} />}<LunarRecommendations timestampUTC={timestampUTC} selected={normalizeLunarSite(Number(simulation.latitude), Number(simulation.longitude))} onSelect={selectRecommendation} onResults={setRecommendations} /><ScientificResults geometry={state.geometry} analysis={state.analysis} metadata={state.metadata} busy={state.loading} attempted={attempted} backendOffline={Boolean(state.health.error)} /></div></main>
    <footer>Science computed by FastAPI / lunar_engine. Visual presentation does not calculate astronomical geometry.</footer></div>;
}
