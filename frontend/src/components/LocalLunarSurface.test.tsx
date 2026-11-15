// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import type { GeometryResponse, ScientificMetadata } from '../api/types';
import { LocalLunarSurface } from './LocalLunarSurface';

const { setSun, dispose, createScene } = vi.hoisted(() => {
  const setSun = vi.fn();
  const dispose = vi.fn();
  const createScene = vi.fn(() => ({ setSun, dispose }));
  return { setSun, dispose, createScene };
});
vi.mock('../babylon/createLocalScene', () => ({ createLocalScene: createScene }));

afterEach(() => { cleanup(); vi.clearAllMocks(); });
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
    expect(screen.getByText(/not actual NASA LOLA elevation data/)).toBeTruthy();
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
    expect(screen.getByRole('status').textContent).toMatch(/Awaiting/);
    mounted.rerender(<LocalLunarSurface {...base} loading={false} geometry={{ value: null, error: 'HTTP 503' }} />);
    expect(screen.getByRole('status').textContent).toContain('HTTP 503');
    expect(setSun).toHaveBeenLastCalledWith(null);
  });
  it('handles Babylon WebGL initialization failures without crashing the dashboard', () => {
    createScene.mockImplementationOnce(() => { throw new Error('No WebGL'); });
    render(<LocalLunarSurface {...base} />);
    expect(screen.getByRole('alert').textContent).toContain('No WebGL');
  });
});
