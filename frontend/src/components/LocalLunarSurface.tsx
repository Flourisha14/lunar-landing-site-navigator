import { useEffect, useMemo, useRef, useState } from 'react';
import type { GeometryResponse, TerrainMeshResponse } from '../api/types';
import type { RequestOutcome } from '../hooks/useLunarAnalysis';
import { ApiError, lunarApi } from '../api/client';
import { createLocalScene, type LocalSceneHandle } from '../babylon/createLocalScene';
import { matchedSolarGeometry } from '../babylon/solarLighting';
import { normalizeLunarSite } from '../globe/lunarCoordinates';

interface Props {
  latitude: string;
  longitude: string;
  timestampUTC: string | null;
  geometry: RequestOutcome<GeometryResponse>;
  loading: boolean;
}

type TerrainState =
  | { status: 'loading' }
  | { status: 'available'; mesh: TerrainMeshResponse; siteKey: string }
  | { status: 'unavailable'; message: string }
  | { status: 'error'; message: string };

export function LocalLunarSurface({ latitude, longitude, timestampUTC, geometry, loading }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<LocalSceneHandle | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [terrain, setTerrain] = useState<TerrainState>({ status: 'loading' });
  const site = useMemo(() => normalizeLunarSite(Number(latitude), Number(longitude)), [latitude, longitude]);
  // Use the normalized site as the request identity, not UTC. Solar updates do not reload terrain.
  const siteKey = site ? `${site.latitudeDeg},${site.longitudeDeg}` : null;
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

  useEffect(() => {
    // Immediately discard the preceding site's geometry, even while the next request is in flight.
    scene.current?.setTerrain(null);
    if (!siteKey) {
      setTerrain({ status: 'unavailable', message: 'Enter a valid lunar latitude and longitude.' });
      return;
    }
    const [latitudeDeg, longitudeDeg] = siteKey.split(',').map(Number);

    // Validate both coordinates before making the API request.
    if (
      latitudeDeg === undefined ||
      longitudeDeg === undefined ||
      !Number.isFinite(latitudeDeg) ||
      !Number.isFinite(longitudeDeg)
    ) {
      setTerrain({
        status: 'unavailable',
        message: 'Invalid lunar coordinates.',
      });
      return;
    }

    const controller = new AbortController();
    setTerrain({ status: 'loading' });
    void lunarApi.terrainMesh({ latitude_deg: latitudeDeg, longitude_deg: longitudeDeg }, controller.signal)
      .then(mesh => {
        if (controller.signal.aborted) return;
        setTerrain({ status: 'available', mesh, siteKey });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.code === 'outside_coverage') {
          setTerrain({ status: 'unavailable', message: 'Selected location is outside the configured NASA LOLA DEM coverage. Choose a site within the supported south-polar region.' });
        } else {
          setTerrain({ status: 'error', message: error instanceof Error ? error.message : 'Terrain data unavailable.' });
        }
      });
    return () => controller.abort();
  }, [siteKey]);

  useEffect(() => {
    if (!ready || !scene.current) return;
    try {
      scene.current.setTerrain(terrain.status === 'available' && terrain.siteKey === siteKey ? terrain.mesh : null);
    } catch (error) {
      scene.current.setTerrain(null);
      setRenderError(error instanceof Error ? error.message : 'Unable to build terrain mesh.');
    }
  }, [ready, terrain, siteKey]);

  useEffect(() => { scene.current?.setSun(solar.value); }, [ready, solar.value]);

  const solarStatus = loading ? 'Awaiting scientific solar geometry…'
    : solar.error ? `Scientific geometry rejected: ${solar.error}`
    : geometry.error ? `Scientific geometry unavailable: ${geometry.error}`
    : !solar.value ? 'No matching scientific solar geometry — directional sunlight disabled.'
    : solar.value.aboveHorizon
      ? `Scientific Sun direction loaded · azimuth ${solar.value.azimuthDeg === null ? 'undefined at zenith' : `${solar.value.azimuthDeg.toFixed(3)}°`} · elevation ${solar.value.elevationDeg.toFixed(3)}°`
      : `Sun at/below horizon (${solar.value.elevationDeg.toFixed(3)}°) — direct sunlight disabled.`;

  return <section className="panel local-surface-panel" aria-label="Babylon local lunar surface">
    <div className="panel-heading"><h2>Local lunar surface</h2><span className="eyebrow">BABYLON · NASA LOLA TERRAIN</span></div>
    <p className="small muted">Selected site: {latitude}°, {longitude}° E · UTC: {timestampUTC ?? 'Invalid UTC input'}</p>
    {!renderError && <canvas ref={canvas} className="local-surface-canvas" aria-label="Babylon local lunar surface canvas" />}
    {renderError && <div role="alert" className="error-panel">WebGL or terrain rendering unavailable: {renderError}</div>}
    <p className="small muted" role="status" data-testid="local-terrain-status">
      {terrain.status === 'loading' ? 'Loading NASA LOLA terrain for selected site…'
        : terrain.status === 'available' ? `NASA LOLA terrain loaded · ${terrain.mesh.status === 'complete' ? 'complete' : 'partial'} coverage · ${terrain.mesh.valid_samples} measured samples · 1× vertical scale.`
        : terrain.status === 'unavailable' ? `Terrain data unavailable: ${terrain.message}`
        : `Terrain API unavailable: ${terrain.message}`}
    </p>
    {terrain.status === 'available' && <p className="tiny muted" data-testid="local-terrain-provenance">
      Dataset: {terrain.mesh.metadata.dataset_id} · DEM: {terrain.mesh.metadata.pixel_size_m} m pixels · center radial elevation: {terrain.mesh.center_elevation_m.toFixed(2)} m.
      Frame: {terrain.mesh.metadata.reference_frame}. {terrain.mesh.metadata.frame_alignment_note}
    </p>}
    <p className="small muted" role="status" data-testid="local-solar-status">{solarStatus}</p>
    {solar.value && <p className="tiny muted">Scientific source: {geometry.value?.metadata.reference_frame}; {geometry.value?.metadata.kernel_manifest_id}. Directional light follows backend ENU; display brightness and UI fill are illustrative.</p>}
    <p className="tiny muted">Drag to orbit and scroll to zoom. Terrain is real DEM geometry only within supported coverage. Sun lighting is directional and visual; terrain-cast shadows, complete terrain-horizon visibility and Earth sky rendering are not yet implemented.</p>
  </section>;
}
