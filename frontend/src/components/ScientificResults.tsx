import type { BodyAssessment, Direction, GeometryResponse, MetadataResponse, ScientificMetadata, SiteAnalysisResponse, VisibilityState } from '../api/types';
import type { RequestOutcome } from '../hooks/useLunarAnalysis';
import { formatDegrees } from '../utils/validation';
import { ErrorPanel } from './ErrorPanel';

interface Props {
  geometry: RequestOutcome<GeometryResponse>;
  analysis: RequestOutcome<SiteAnalysisResponse>;
  metadata: RequestOutcome<MetadataResponse>;
  busy: boolean;
  attempted: boolean;
  backendOffline: boolean;
}

function Visibility({ value }: { value: VisibilityState | null | undefined }) {
  return value ? <span className={`visibility ${value}`}>{value.toUpperCase()}</span> : <span className="muted">—</span>;
}
function Field({ title, value }: { title: string; value: string | number | null | undefined }) {
  return <div className="data-row"><dt>{title}</dt><dd>{value ?? '—'}</dd></div>;
}
function BodyCard({ name, geometry, assessment, mode }: { name: 'SUN' | 'EARTH'; geometry?: Direction; assessment?: BodyAssessment; mode?: string }) {
  // Prefer site-analysis angles for the terrain result; geometry uses a reference sphere.
  const azimuth = assessment ? assessment.azimuth_deg : geometry?.azimuth_deg;
  const elevation = assessment ? assessment.elevation_deg : geometry?.elevation_deg;
  return <section className="body-card"><h3>{name === 'SUN' ? '☀ Sun' : '◉ Earth'}</h3>
    <dl><Field title="Azimuth (clockwise from north)" value={azimuth === undefined ? '—' : formatDegrees(azimuth)} />
      <Field title="Elevation" value={elevation === undefined ? '—' : formatDegrees(elevation)} />
      <div className="data-row"><dt>Geometric visibility</dt><dd><Visibility value={assessment?.geometric_visibility ?? geometry?.geometric_visibility} /></dd></div>
      <div className="data-row"><dt>{mode === 'geometric' ? 'Selected-mode visibility' : 'Terrain-aware visibility'}</dt><dd>{assessment ? <Visibility value={assessment.status} /> : <span className="muted">—</span>}</dd></div>
      {mode === 'terrain_aware' && <><Field title="Terrain horizon" value={assessment ? assessment.terrain_horizon_deg == null ? 'Unknown / unavailable' : formatDegrees(assessment.terrain_horizon_deg) : '—'} />
        <Field title="Horizon clearance" value={assessment ? assessment.clearance_deg == null ? 'Unknown / unavailable' : formatDegrees(assessment.clearance_deg) : '—'} />
        <Field title="Horizon samples" value={assessment ? `${assessment.horizon_samples_completed ?? '—'} / ${assessment.horizon_samples_requested ?? '—'}` : '—'} /></>}
      {assessment?.reason && <Field title="Scientific note" value={assessment.reason} />}
    </dl>
  </section>;
}
function Provenance({ science, apiMetadata }: { science?: ScientificMetadata; apiMetadata?: MetadataResponse }) {
  return <section className="panel provenance"><div className="panel-heading"><h2>Scientific provenance</h2><span className="eyebrow">SOURCE TRANSPARENCY</span></div>
    <dl><Field title="Reference frame" value={science?.reference_frame ?? apiMetadata?.reference_frame} />
      <Field title="SPICE kernel manifest" value={science?.kernel_manifest_id} />
      <Field title="Terrain dataset" value={science ? science.terrain_dataset_id ?? 'None for this result' : apiMetadata?.terrain_dataset_id ?? '—'} />
      <Field title="Calculation mode" value={science?.mode} />
      <Field title="Fidelity" value={science?.fidelity} />
      <Field title="Aberration correction" value={science?.aberration} />
      <Field title="Coordinates" value={science ? `${science.latitude_type}, longitude positive ${science.longitude_positive}` : apiMetadata?.coordinate_convention} />
    </dl>
    {(science?.limitations ?? apiMetadata?.limitations)?.length ? <div className="limitations"><strong>Scientific limitations</strong><ul>{(science?.limitations ?? apiMetadata?.limitations ?? []).map((line, index) => <li key={index}>{line}</li>)}</ul></div> : null}
  </section>;
}
export function ScientificResults({ geometry, analysis, metadata, busy, attempted, backendOffline }: Props) {
  const science = analysis.value?.metadata ?? geometry.value?.metadata;
  const mode = analysis.value?.metadata.mode;
  const terrainDataset = analysis.value?.metadata.terrain_dataset_id ?? metadata.value?.terrain_dataset_id;
  const terrainCoverage = !attempted ? 'Not evaluated'
    : analysis.value == null ? 'Not determined'
    : mode === 'geometric' ? 'Not applicable (geometric mode)'
    : [analysis.value.sun, analysis.value.earth].some(body => body.status === 'unknown') ? 'Incomplete / unknown for ≥1 target'
    : 'Sightline analysis reported for both targets';

  return <div className="results-column">
    <section className="panel results-panel"><div className="panel-heading"><h2>Scientific analysis</h2><span className="eyebrow">BACKEND RESULTS ONLY</span></div>
      {backendOffline && (geometry.value || analysis.value) && (
        <div className="error-panel" role="status" aria-live="polite">
          <strong>PREVIOUS ANALYSIS — BACKEND OFFLINE</strong>
          <p>
            These scientific results were calculated earlier.
            The backend is currently disconnected.
            Reconnect to perform a new analysis.
          </p>
        </div>
      )}
      {busy && <p className="loading" role="status">Querying NASA SPICE / terrain science backend…</p>}
      {!attempted && !busy && <p className="muted intro">Select a site and UTC time, then analyze to request scientific results.</p>}
      {geometry.error && <ErrorPanel title="Geometry request failed" message={geometry.error} />}
      {analysis.error && <ErrorPanel title="Site analysis failed" message={analysis.error} />}
      {attempted && !analysis.value && geometry.value && <p className="notice">Geometry below comes from the reference-sphere endpoint only. Terrain-aware visibility is not available; no fallback was applied.</p>}
      {geometry.value && analysis.value && <p className="tiny muted">Displayed angles use site-analysis results. The separately requested geometry endpoint uses reference-sphere elevation 0 m and can produce different angles from DEM-surface results.</p>}
      {(geometry.value || analysis.value) && <p className="tiny timestamp">UTC: {analysis.value?.timestamp_utc ?? geometry.value?.timestamp_utc} · Site: {analysis.value?.latitude_deg ?? geometry.value?.latitude_deg}°, {analysis.value?.longitude_deg ?? geometry.value?.longitude_deg}° E</p>}
      <div className="body-grid"><BodyCard name="SUN" geometry={geometry.value?.sun} assessment={analysis.value?.sun} mode={mode} />
        <BodyCard name="EARTH" geometry={geometry.value?.earth} assessment={analysis.value?.earth} mode={mode} /></div>
      <div className="terrain-status"><h3>Terrain coverage</h3><dl><Field title="Analysis status" value={terrainCoverage} />
        <Field title="Configured dataset" value={terrainDataset ?? 'Not configured / not reported'} />
        <Field title="Terrain configured" value={metadata.value ? metadata.value.terrain_configured ? 'Yes' : 'No' : 'Unknown'} /></dl>
        <p className="tiny muted">A completed sightline is not a complete global DEM coverage certification. See each target's state and reason.</p>
      </div>
      <p className="notice">Geometric Earth visibility is not a verified radio link or guaranteed communication. No link budget, pointing constraints, or radio propagation are calculated.</p>
    </section>
    {metadata.error && <ErrorPanel title="Metadata request failed" message={metadata.error} />}
    <Provenance science={science} apiMetadata={metadata.value ?? undefined} />
  </div>;
}
