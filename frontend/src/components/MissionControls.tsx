import type { FormEvent } from 'react';
import type { SimulationState } from '../state/simulation';

interface Props {
  value: SimulationState;
  onChange: (value: SimulationState) => void;
  onAnalyze: () => void;
  busy: boolean;
}

export function MissionControls({ value, onChange, onAnalyze, busy }: Props) {
  const update = <K extends keyof SimulationState>(key: K, val: SimulationState[K]) => onChange({ ...value, [key]: val });
  const submit = (event: FormEvent) => { event.preventDefault(); onAnalyze(); };
  return (
    <section className="panel controls-panel">
      <div className="panel-heading"><h2>Mission controls</h2><span className="eyebrow">INPUT PARAMETERS</span></div>
      <form onSubmit={submit} noValidate>
        <div className="field-grid">
          <label>Latitude (°)<input type="number" value={value.latitude} min={-90} max={90} step="any" required onChange={e => update('latitude', e.target.value)} /></label>
          <label>Longitude (° E)<input type="number" value={value.longitude} step="any" required onChange={e => update('longitude', e.target.value)} /></label>
          <label>Date (UTC)<input type="date" value={value.dateUTC} required onChange={e => update('dateUTC', e.target.value)} /></label>
          <label>Time (UTC)<input type="time" step="60" value={value.timeUTC} required onChange={e => update('timeUTC', e.target.value)} /></label>
          <label>Observer height (m)<input type="number" min="0" max="100000" step="any" value={value.observerHeight} required onChange={e => update('observerHeight', e.target.value)} /></label>
          <label>Analysis mode<select value={value.mode} onChange={e => update('mode', e.target.value as SimulationState['mode'])}><option value="terrain_aware">Terrain-aware</option><option value="geometric">Geometric</option></select></label>
        </div>
        {value.mode === 'terrain_aware' && <fieldset className="terrain-options"><legend>Terrain sampling</legend><div className="field-grid">
          <label>Max distance (km)<input type="number" min="0" max="1000" step="any" value={value.maxDistanceKm} onChange={e => update('maxDistanceKm', e.target.value)} /></label>
          <label>Sampling step (m)<input type="number" min="0" max="100000" step="any" value={value.stepM} onChange={e => update('stepM', e.target.value)} /></label>
          <label>Interpolation<select value={value.interpolation} onChange={e => update('interpolation', e.target.value as SimulationState['interpolation'])}><option value="bilinear">Bilinear</option><option value="nearest">Nearest</option></select></label>
        </div></fieldset>}
        <p className="tiny muted">Latitude is planetocentric; longitude is east-positive. Input time is UTC, never browser-local time.</p>
        <button className="primary" type="submit" disabled={busy}>{busy ? 'Analyzing scientific data…' : 'Analyze site →'}</button>
      </form>
    </section>
  );
}
