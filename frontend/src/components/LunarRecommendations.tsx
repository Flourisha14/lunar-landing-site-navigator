import { useEffect, useRef, useState } from 'react';
import { ApiError, lunarApi } from '../api/client';
import type { RecommendSitesRequest, RecommendSitesResponse, ScreenedCandidate } from '../recommendations/types';
import { durationHours, fractionPercent, parseRecommendations, utcFromInput, validateMission } from '../recommendations/types';
import type { LunarSite } from '../globe/lunarCoordinates';
import { normalizeLunarSite } from '../globe/lunarCoordinates';

interface Props {
  timestampUTC: string | null;
  selected: LunarSite | null;
  onSelect: (site: LunarSite) => void;
  onResults: (results: RecommendSitesResponse | null) => void;
}
const controlStyle = { width: '100%', minWidth: 0 };
const gridStyle = { display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: '12px' };
const labelStyle = { display: 'grid', gap: '5px', fontSize: '0.8rem' };
const defaults = (timestampUTC: string | null): RecommendSitesRequest => ({
  start_utc: timestampUTC ?? new Date().toISOString(),
  duration_hours: 24, sampling_seconds: 3600, candidate_count: 8, max_recommendations: 5,
  observer_height_m: 2,
  terrain: { max_distance_km: 2, step_m: 160, interpolation: 'bilinear' },
  constraints: {
    min_sun_fraction: 0.5, min_earth_fraction: 0.5, min_simultaneous_fraction: 0.25,
    max_darkness_seconds: null, max_earth_outage_seconds: null,
  },
});

export function LunarRecommendations({ timestampUTC, selected, onSelect, onResults }: Props) {
  const [config, setConfig] = useState<RecommendSitesRequest>(() => defaults(timestampUTC));
  const [start, setStart] = useState(() => (timestampUTC ?? new Date().toISOString()).slice(0, 16));
  const [result, setResult] = useState<RecommendSitesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);
  const serial = useRef(0);
  const onResultsRef = useRef(onResults);
  useEffect(() => { onResultsRef.current = onResults; }, [onResults]);
  useEffect(() => () => { active.current?.abort(); serial.current += 1; }, []);
  const update = <K extends keyof RecommendSitesRequest>(key: K, value: RecommendSitesRequest[K]) => {
    setConfig(previous => ({ ...previous, [key]: value }));
    active.current?.abort(); serial.current += 1;
    setResult(null); onResultsRef.current(null); setLoading(false);
  };
  const updateTerrain = (key: keyof RecommendSitesRequest['terrain'], value: number) => {
    update('terrain', { ...config.terrain, [key]: value });
  };
  const updateConstraint = (key: keyof RecommendSitesRequest['constraints'], value: number | null) => {
    update('constraints', { ...config.constraints, [key]: value });
  };
  const changeStart = (value: string) => {
    setStart(value);
    active.current?.abort(); serial.current += 1;
    setResult(null); onResultsRef.current(null); setLoading(false);
  };
  const run = async () => {
    const formatted = utcFromInput(start);
    if (!formatted) { setError('Enter a valid UTC mission start time.'); return; }
    const request: RecommendSitesRequest = { ...config, start_utc: formatted };
    const message = validateMission(request);
    if (message) { setError(message); return; }
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    const sequence = ++serial.current;
    setError(null); setResult(null); onResultsRef.current(null); setLoading(true);
    try {
      const raw = await lunarApi.recommendSites(request, controller.signal);
      const checked = parseRecommendations(raw);
      if (sequence !== serial.current || controller.signal.aborted) return;
      setResult(checked); onResultsRef.current(checked);
    } catch (e) {
      if (sequence !== serial.current || controller.signal.aborted) return;
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Recommendation request failed.');
    } finally {
      if (sequence === serial.current) setLoading(false);
    }
  };
  const choose = (site: ScreenedCandidate) => {
    const normalized = normalizeLunarSite(site.latitude_deg, site.longitude_deg);
    if (normalized) onSelect(normalized);
  };
  const numberField = (label: string, value: number, onChange: (v: number) => void, min: number, max?: number, step = 1) => (
    <label style={labelStyle}>{label}<input style={controlStyle} type="number" min={min} max={max} step={step} value={value}
      onChange={event => onChange(event.target.value === '' ? NaN : Number(event.target.value))} /></label>
  );
  return <section className="panel" aria-label="Physics-Based Site Recommendations" data-testid="recommendation-panel" style={{ marginTop: 14 }}>
    <div className="panel-heading"><h2>Physics-Based Site Recommendations</h2><span className="eyebrow">LUNAR INTELLIGENCE</span></div>
    <p className="small muted">Candidate locations are screened using modeled solar illumination and geometric Earth visibility within the available lunar terrain dataset. Results are preliminary and do not certify landing safety.</p>
    <div style={gridStyle}>
      <label style={labelStyle}>Mission start (UTC)<input type="datetime-local" value={start} onChange={e => changeStart(e.target.value)} style={controlStyle} /></label>
      {numberField('Duration (hours)', config.duration_hours, v => update('duration_hours', v), 1, 2160)}
      {numberField('Sampling (seconds)', config.sampling_seconds, v => update('sampling_seconds', v), 1)}
      {numberField('Candidate sites (1–12)', config.candidate_count, v => update('candidate_count', v), 1, 12)}
      {numberField('Maximum recommendations', config.max_recommendations, v => update('max_recommendations', v), 1, 12)}
      {numberField('Observer height (m)', config.observer_height_m, v => update('observer_height_m', v), 0, 100000)}
    </div>
    <details style={{ marginTop: 12 }}><summary>Advanced terrain and mission constraints</summary>
      <div style={{ ...gridStyle, marginTop: 12 }}>
        {numberField('Horizon search radius (km)', config.terrain.max_distance_km, v => updateTerrain('max_distance_km', v), 0.01, 20, 0.1)}
        {numberField('Horizon sampling step (m)', config.terrain.step_m, v => updateTerrain('step_m', v), 1, 100000)}
        {(['min_sun_fraction', 'min_earth_fraction', 'min_simultaneous_fraction'] as const).map((key, i) =>
          <div key={key}>{numberField(['Minimum Sun visibility (%)', 'Minimum Earth visibility (%)', 'Minimum simultaneous (%)'][i] ?? key,
            Math.round(config.constraints[key] * 100), v => updateConstraint(key, v / 100), 0, 100)}</div>)}
        {(['max_darkness_seconds', 'max_earth_outage_seconds'] as const).map((key, i) =>
          <label key={key} style={labelStyle}>{i === 0 ? 'Maximum darkness (hours; optional)' : 'Maximum Earth outage (hours; optional)'}
            <input style={controlStyle} type="number" min={0} placeholder="No limit" value={config.constraints[key] === null ? '' : config.constraints[key]! / 3600}
              onChange={e => updateConstraint(key, e.target.value === '' ? null : Number(e.target.value) * 3600)} />
          </label>)}
      </div>
    </details>
    <button type="button" onClick={() => void run()} disabled={loading} style={{ marginTop: 12 }}>{loading ? 'Screening sites…' : 'Recommend landing sites →'}</button>
    {loading && <p role="status">Scientific backend is evaluating candidate locations…</p>}
    {error && <div role="alert" className="error-panel">{error} <button type="button" onClick={() => void run()}>Retry</button></div>}
    {result && <div style={{ marginTop: 16 }}>
      <p className="small muted">Evaluated {result.evaluated_count} candidates · {result.suitable_count} suitable · {result.unsuitable_count} unsuitable · {result.insufficient_count} insufficient data.</p>
      {result.resolution === 'no_suitable_candidates' && <p role="status">No suitable sites found among the evaluated candidates for this date.</p>}
      {result.resolution === 'insufficient_data' && <p role="status">Insufficient scientific data to support a definitive recommendation.</p>}
      {result.recommendations.length > 0 && <><h3>Ranked recommendations</h3><p className="tiny muted">Scores reflect modeled visibility and mission preferences. Equal scores indicate no modeled score advantage; backend tie-breaks are deterministic.</p>
        <div style={{ display: 'grid', gap: 10 }}>
          {result.recommendations.map((item, index) => <article key={`${item.latitude_deg},${item.longitude_deg}`} className="panel" style={{ padding: 12 }}>
            <strong>#{index + 1} · {item.score === null ? 'Unknown score' : `Score ${item.score.toFixed(3)}`}</strong>
            <p className="small muted">{item.latitude_deg.toFixed(5)}° · {item.longitude_deg.toFixed(5)}° E {selected && selected.latitudeDeg === item.latitude_deg && selected.longitudeDeg === item.longitude_deg ? '(selected)' : ''}</p>
            <p className="small">Sun {fractionPercent(item.sun_fraction)} · Earth {fractionPercent(item.earth_fraction)} · Both {fractionPercent(item.simultaneous_fraction)}</p>
            <p className="tiny muted">Longest darkness {durationHours(item.longest_darkness_seconds)} · Earth outage {durationHours(item.longest_earth_outage_seconds)}</p>
            <p className="tiny muted">Checks: {Object.entries(item.checks).map(([name, passed]) => `${name}: ${passed === null ? 'unknown' : passed ? 'pass' : 'fail'}`).join(' · ')}</p>
            <button type="button" className="secondary" onClick={() => choose(item)}>Select and analyze site</button>
          </article>)}
        </div></>}
      <details style={{ marginTop: 14 }}><summary>All evaluated sites ({result.candidates.length})</summary>
        {result.candidates.map((item, index) => <p key={`${index}-${item.latitude_deg}-${item.longitude_deg}`} className="small">
          <strong>{item.suitability}</strong> · {item.latitude_deg.toFixed(4)}°, {item.longitude_deg.toFixed(4)}° E · {fractionPercent(item.sun_fraction)} Sun
          <button type="button" className="secondary" onClick={() => choose(item)}>Select</button>
        </p>)}
      </details>
      <details style={{ marginTop: 12 }}><summary>Scientific explanation and provenance</summary>
        <p className="small">Scope: {result.screening_scope} · Fidelity: {result.fidelity}</p>
        <p className="small">Dataset: {result.dataset_id} · Frame: {result.reference_frame} · Kernel manifest: {result.kernel_manifest_id ?? 'Unavailable'}</p>
        <p className="small">UTC: {result.start_utc} – {result.end_utc} · Step: {result.sampling_seconds} s · Processing: {result.processing_seconds}s</p>
        <p className="small">Constraints: {JSON.stringify(result.constraints)} · Weights: {JSON.stringify(result.weights)}</p>
        {result.candidates.map((site, i) => <p className="tiny muted" key={i}>{site.latitude_deg.toFixed(4)}°, {site.longitude_deg.toFixed(4)}°: {site.explanation} · Unknown Sun/Earth/Both samples: {site.unknown_sun_samples ?? 'n/a'}/{site.unknown_earth_samples ?? 'n/a'}/{site.unknown_simultaneous_samples ?? 'n/a'} of {site.total_samples ?? 'n/a'}</p>)}
        {result.limitations.map((limitation, i) => <p className="tiny muted" key={i}>• {limitation}</p>)}
      </details>
    </div>}
  </section>;
}
