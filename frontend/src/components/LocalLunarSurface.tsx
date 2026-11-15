import { useEffect, useMemo, useRef, useState } from 'react';
import type { GeometryResponse } from '../api/types';
import type { RequestOutcome } from '../hooks/useLunarAnalysis';
import { createLocalScene, type LocalSceneHandle } from '../babylon/createLocalScene';
import { matchedSolarGeometry } from '../babylon/solarLighting';

interface Props {
  latitude: string;
  longitude: string;
  timestampUTC: string | null;
  geometry: RequestOutcome<GeometryResponse>;
  loading: boolean;
}

export function LocalLunarSurface({ latitude, longitude, timestampUTC, geometry, loading }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<LocalSceneHandle | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const solar = useMemo(() => {
    try {
      return { value: matchedSolarGeometry(geometry.value, latitude, longitude, timestampUTC), error: null };
    } catch (error) {
      return { value: null, error: error instanceof Error ? error.message : String(error) };
    }
  }, [geometry.value, latitude, longitude, timestampUTC]);

  useEffect(() => {
    if (!canvas.current) return;
    try {
      scene.current = createLocalScene(canvas.current);
      setReady(true);
    } catch (error) {
      setRenderError(error instanceof Error ? error.message : String(error));
    }
    return () => {
      scene.current?.dispose();
      scene.current = null;
    };
  }, []);

  useEffect(() => { scene.current?.setSun(solar.value); }, [ready, solar.value]);

  const status = loading ? 'Awaiting scientific solar geometry…'
    : solar.error ? `Scientific geometry rejected: ${solar.error}`
    : geometry.error ? `Scientific geometry unavailable: ${geometry.error}`
    : !solar.value ? 'No matching scientific solar geometry — directional sunlight disabled.'
    : solar.value.aboveHorizon
      ? `Scientific Sun direction loaded · azimuth ${solar.value.azimuthDeg === null ? 'undefined at zenith' : `${solar.value.azimuthDeg.toFixed(3)}°`} · elevation ${solar.value.elevationDeg.toFixed(3)}°`
      : `Sun at/below horizon (${solar.value.elevationDeg.toFixed(3)}°) — direct sunlight disabled.`;

  return <section className="panel local-surface-panel" aria-label="Babylon local lunar surface">
    <div className="panel-heading"><h2>Local lunar surface</h2><span className="eyebrow">BABYLON · ILLUSTRATIVE TERRAIN</span></div>
    <p className="small muted">Selected site: {latitude}°, {longitude}° E · UTC: {timestampUTC ?? 'Invalid UTC input'}</p>
    <p className="notice"><strong>Illustrative terrain — not actual NASA LOLA elevation data.</strong> Generated rocks, terrain appearance, and shadows are not scientifically validated.</p>
    {!renderError && <canvas ref={canvas} className="local-surface-canvas" aria-label="Babylon local lunar surface canvas" />}
    {renderError && <div role="alert" className="error-panel">WebGL local viewer unavailable: {renderError}</div>}
    <p className="small muted" role="status" data-testid="local-solar-status">{status}</p>
    {solar.value && <p className="tiny muted">Scientific source: {geometry.value?.metadata.reference_frame}; {geometry.value?.metadata.kernel_manifest_id}. Directional light follows backend ENU; display brightness and UI fill are illustrative.</p>}
    <p className="tiny muted">Drag to orbit and scroll to zoom. This scene does not render the actual DEM, terrain horizon or mission-certified shadows.</p>
  </section>;
}
