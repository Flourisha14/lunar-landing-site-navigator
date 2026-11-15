// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import type { GeometryResponse, ScientificMetadata } from '../api/types';
import { LocalLunarSurface } from './LocalLunarSurface';

const { setSun, setTerrain, dispose, createScene } = vi.hoisted(() => {
  const setSun = vi.fn();
  const setTerrain = vi.fn();
  const dispose = vi.fn();
  const createScene = vi.fn(() => ({ setSun, setTerrain, dispose }));
  return { setSun, setTerrain, dispose, createScene };
});
vi.mock('../babylon/createLocalScene', () => ({ createLocalScene: createScene }));
const { terrainMesh } = vi.hoisted(() => ({ terrainMesh: vi.fn() }));
vi.mock('../api/client', () => ({ lunarApi: { terrainMesh: (...args: unknown[]) => terrainMesh(...args) }, ApiError: class ApiError extends Error { constructor(message: string, public status: number, public code: string) { super(message); } } }));

afterEach(() => { cleanup(); vi.clearAllMocks(); });
// By default this fixture selects an unsupported site; no terrain may be generated.
beforeEach(() => {
  terrainMesh.mockRejectedValue(new Error('Controlled terrain unavailable'));
});
const metadata: ScientificMetadata = {
  api_version: 'v1', reference_frame: 'MOON_ME_DE421', kernel_manifest_id: 'E2E-fixture',
  terrain_dataset_id: null, mode: 'geometry', aberration: 'NONE', fidelity: 'fixture',
  limitations: [], latitude_type: 'planetocentric', longitude_positive: 'east',
  angular_unit: 'deg', horizontal_distance_unit: 'km', height_unit: 'm',
};
const geometry = {
  latitude_deg: -89.5, longitude_deg: 45, timestamp_utc: '2027-11-15T12:00:00Z', metadata,
  sun: { body: 'SUN', east_unit: 0, north_unit: 0, up_unit: 1, azimuth_deg: null,
    elevation_deg: 90, range_km: 1000, position_moon_fixed_km: [0, 0, 0], geometric_visibility: 'visible' },
} as GeometryResponse;
const base = {
  latitude: '-89.5', longitude: '45', timestampUTC: '2027-11-15T12:00:00Z',
  geometry: { value: geometry, error: null }, loading: false,
};

describe('LocalLunarSurface component, GPU-independent', () => {
  it('mounts one canvas/scene, conveys scientific light and disposes on unmount', async () => {
    const mounted = render(<LocalLunarSurface {...base} />);
    expect(screen.getByLabelText('Babylon local lunar surface canvas')).toBeTruthy();
    expect(screen.getByText(/BABYLON · NASA LOLA TERRAIN/)).toBeTruthy();
    expect(createScene).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(setSun).toHaveBeenCalledWith(expect.objectContaining({ aboveHorizon: true })));
    mounted.unmount();
    expect(dispose).toHaveBeenCalledTimes(1);
  });
  it('does not use stale scientific light after UTC or coordinate changes', async () => {
    const mounted = render(<LocalLunarSurface {...base} />);
    mounted.rerender(<LocalLunarSurface {...base} timestampUTC="2027-11-16T12:00:00Z" />);
    await waitFor(() => expect(setSun).toHaveBeenLastCalledWith(null));
    mounted.rerender(<LocalLunarSurface {...base} latitude="-85" />);
    await waitFor(() => expect(setSun).toHaveBeenLastCalledWith(null));
    expect(createScene).toHaveBeenCalledTimes(1);
  });
  it('shows loading, science errors and missing geometry without fabricated sun', () => {
    const mounted = render(<LocalLunarSurface {...base} loading={true} />);
    expect(screen.getByTestId('local-solar-status').textContent).toMatch(/Awaiting/);
    mounted.rerender(<LocalLunarSurface {...base} loading={false} geometry={{ value: null, error: 'HTTP 503' }} />);
    expect(screen.getByTestId('local-solar-status').textContent).toContain('HTTP 503');
    expect(setSun).toHaveBeenLastCalledWith(null);
  });
  it('handles Babylon WebGL initialization failures without crashing the dashboard', () => {
    createScene.mockImplementationOnce(() => { throw new Error('No WebGL'); });
    render(<LocalLunarSurface {...base} />);
    expect(screen.getByRole('alert').textContent).toContain('No WebGL');
  });
  it('shows unavailable data without creating synthetic terrain', async () => {
    render(<LocalLunarSurface {...base} />);
    await waitFor(() => expect(screen.getByTestId('local-terrain-status').textContent).toContain('Terrain API unavailable'));
    expect(setTerrain).toHaveBeenCalledWith(null);
    expect(setTerrain).not.toHaveBeenCalledWith(expect.objectContaining({ vertices: expect.anything() }));
  });
  it('requests the selected site and keeps terrain stable when only UTC changes', async () => {
    terrainMesh.mockImplementation(() => new Promise(() => undefined));
    const mounted = render(<LocalLunarSurface {...base} />);
    expect(terrainMesh).toHaveBeenCalledWith({ latitude_deg: -89.5, longitude_deg: 45 }, expect.any(AbortSignal));
    mounted.rerender(<LocalLunarSurface {...base} timestampUTC="2027-11-16T12:00:00Z" />);
    expect(terrainMesh).toHaveBeenCalledTimes(1);
  });
});
