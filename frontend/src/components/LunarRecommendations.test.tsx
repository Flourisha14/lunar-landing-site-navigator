// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { LunarRecommendations } from './LunarRecommendations';
import { lunarApi } from '../api/client';
import type { RecommendSitesResponse } from '../recommendations/types';

vi.mock('../api/client', async () => {
  class ApiError extends Error { constructor(message: string, public status: number | null = null) { super(message); } }
  return { ApiError, lunarApi: { recommendSites: vi.fn() } };
});
const recommendSites = vi.mocked(lunarApi.recommendSites);
const site = {
  latitude_deg: -89.5, longitude_deg: 45, suitability: 'SUITABLE', score: 1,
  sun_fraction: 1, earth_fraction: 1, simultaneous_fraction: 1,
  longest_darkness_seconds: 0, longest_earth_outage_seconds: 0,
  unknown_sun_samples: 0, unknown_earth_samples: 0, unknown_simultaneous_samples: 0,
  total_samples: 24, checks: { sunlight: true }, explanation: 'Modeled visibility passes thresholds',
  terrain_dataset_id: 'LOLA', reference_frame: 'MOON_ME_DE421', kernel_manifest_id: 'kernel',
} as const;
const result = {
  api_version: 'v1', start_utc: '2027-11-15T12:00:00Z', end_utc: '2027-11-16T12:00:00Z', sampling_seconds: 3600,
  constraints: { min_sun_fraction: .5, min_earth_fraction: .5, min_simultaneous_fraction: .25, max_darkness_seconds: null, max_earth_outage_seconds: null },
  terrain: { max_distance_km: 2, step_m: 160, interpolation: 'bilinear' }, candidate_count: 8,
  requested_recommendations: 5, generated_count: 1, evaluated_count: 1,
  suitable_count: 1, unsuitable_count: 0, insufficient_count: 0,
  resolution: 'suitable_candidates', candidates: [site], recommendations: [site],
  dataset_id: 'LOLA', reference_frame: 'MOON_ME_DE421', kernel_manifest_id: 'kernel',
  weights: { sun: .4 }, screening_scope: 'DEM only', fidelity: 'sampled', processing_seconds: .1,
  limitations: ['Screening only'],
} as const;
const props = () => ({ timestampUTC: '2027-11-15T12:00:00Z', selected: null, onSelect: vi.fn(), onResults: vi.fn() });
beforeEach(() => { recommendSites.mockReset(); });
afterEach(() => cleanup());
describe('physics-based site recommendation UI', () => {
  it('serializes backend defaults without a separate ranking algorithm', async () => {
    recommendSites.mockResolvedValue(result as never);
    render(<LunarRecommendations {...props()} />);
    fireEvent.click(screen.getByRole('button', { name: /Recommend landing sites/ }));
    await waitFor(() => expect(recommendSites).toHaveBeenCalledOnce());
    expect(recommendSites.mock.calls[0]?.[0]).toMatchObject({ duration_hours: 24, sampling_seconds: 3600,
      candidate_count: 8, max_recommendations: 5, start_utc: '2027-11-15T12:00:00Z' });
    expect(await screen.findByText(/Score 1.000/)).toBeTruthy();
  });
  it('selects backend coordinates without changing the UTC', async () => {
    recommendSites.mockResolvedValue(result as never);
    const handlers = props();
    render(<LunarRecommendations {...handlers} />);
    fireEvent.click(screen.getByRole('button', { name: /Recommend landing sites/ }));
    fireEvent.click(await screen.findByRole('button', { name: /Select and analyze site/ }));
    expect(handlers.onSelect).toHaveBeenCalledWith({ latitudeDeg: -89.5, longitudeDeg: 45 });
  });
  it('shows backend failure with retry', async () => {
    recommendSites.mockRejectedValue(new Error('Backend offline'));
    render(<LunarRecommendations {...props()} />);
    fireEvent.click(screen.getByRole('button', { name: /Recommend landing sites/ }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Backend offline'));
  });
  it('does not apply a stale request after settings change', async () => {
    let resolveRequest!: (value: RecommendSitesResponse) => void;
    recommendSites.mockImplementation(() => new Promise<RecommendSitesResponse>(resolve => { resolveRequest = resolve; }));
    const handlers = props();
    render(<LunarRecommendations {...handlers} />);
    fireEvent.click(screen.getByRole('button', { name: /Recommend landing sites/ }));
    await waitFor(() => expect(recommendSites).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText('Duration (hours)'), { target: { value: '12' } });
    resolveRequest(result as unknown as RecommendSitesResponse);
    await waitFor(() => expect(screen.queryByText(/Score 1.000/)).toBeNull());
    expect(handlers.onResults).not.toHaveBeenCalledWith(result);
  });
});
