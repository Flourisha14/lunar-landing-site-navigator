import { API_BASE_URL } from '../api/client';
import type { HealthResponse } from '../api/types';
import type { RequestOutcome } from '../hooks/useLunarAnalysis';

interface Props {
  health: RequestOutcome<HealthResponse>;
  checking: boolean;
  onRetry: () => void;
}

export function BackendStatus({ health, checking, onRetry }: Props) {
  const connected = !!health.value;
  const scienceReady = health.value?.science_available === true;
  return (
    <section className="panel status-panel" aria-label="Backend connection">
      <div className="panel-heading"><h2>Scientific backend</h2><span className={`status-pill ${connected ? 'online' : 'offline'}`}>{checking ? 'CHECKING' : connected ? 'API CONNECTED' : 'DISCONNECTED'}</span></div>
      <p className="muted api-url">{API_BASE_URL}</p>
      <p className="small">Science resources: <strong>{checking ? 'Checking…' : !connected ? 'Unknown' : scienceReady ? 'Reported available' : 'Not fully available'}</strong></p>
      <p className="small muted">{health.value?.detail ?? health.error ?? 'Contacting health endpoint…'}</p>
      <p className="tiny muted">Health reports manifest presence; actual kernel coverage is checked during analysis.</p>
      <button className="secondary" type="button" disabled={checking} onClick={onRetry}>Recheck connection</button>
    </section>
  );
}
