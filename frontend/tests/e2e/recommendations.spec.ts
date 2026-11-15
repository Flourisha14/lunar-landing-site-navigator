import { expect, test } from '@playwright/test';

// Controlled browser fixture: tests UI integration, not SPICE/LOLA numerics.
// No live scientific service, Cesium ion token, or external datasets required.
test('recommendations select a site through Mission Controls and the Cesium globe', async ({ page }) => {
  const latitude = -89.3;
  const longitude = 40;
  const recommendationRequests: Record<string, unknown>[] = [];
  const siteAnalysisRequests: Record<string, unknown>[] = [];
  const geometryRequests: Record<string, unknown>[] = [];

  await page.route('**/api/v1/health', route => route.fulfill({ json: {
    status: 'ok', api_version: 'v1', science_available: true,
    detail: 'Controlled browser fixture',
  } }));
  await page.route('**/api/v1/metadata', route => route.fulfill({ json: {
    api_version: 'v1', modes: ['geometric', 'terrain_aware'],
    supported_targets: ['SUN', 'EARTH'], reference_frame: 'MOON_ME_DE421',
    coordinate_convention: 'Planetocentric; east-positive',
    terrain_dataset_id: 'LOLA-browser-fixture', terrain_configured: true,
    kernel_manifests_configured: true, max_timeline_samples: 2048,
    max_timeline_days: 90, limitations: ['Browser fixture — no scientific predictions'],
  } }));
  await page.route('**/api/v1/geometry', route => {
    geometryRequests.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({ status: 503, json: {
      code: 'scientific_data_unavailable', detail: 'Controlled browser fixture: geometry unavailable',
    } });
  });
  await page.route('**/api/v1/site-analysis', route => {
    siteAnalysisRequests.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({ status: 422, json: {
      code: 'terrain_coverage_error', detail: 'Controlled browser fixture: no DEM rays',
    } });
  });

  const constraints = {
    min_sun_fraction: 0.5, min_earth_fraction: 0.5,
    min_simultaneous_fraction: 0.25, max_darkness_seconds: null,
    max_earth_outage_seconds: null,
  };
  const terrain = { max_distance_km: 2, step_m: 160, interpolation: 'bilinear' };
  const suitable = {
    latitude_deg: latitude, longitude_deg: longitude,
    suitability: 'SUITABLE', score: 1,
    sun_fraction: 1, earth_fraction: 1, simultaneous_fraction: 1,
    longest_darkness_seconds: 0, longest_earth_outage_seconds: 0,
    unknown_sun_samples: 0, unknown_earth_samples: 0,
    unknown_simultaneous_samples: 0, total_samples: 24,
    checks: { sunlight: true, earth: true, simultaneous: true },
    explanation: 'Controlled fixture: modeled thresholds satisfied',
    terrain_dataset_id: 'LOLA-browser-fixture', reference_frame: 'MOON_ME_DE421',
    kernel_manifest_id: 'browser-fixture',
  };
  const unsuitable = {
    ...suitable, latitude_deg: -89.35, longitude_deg: 38,
    suitability: 'UNSUITABLE', score: 0.2, sun_fraction: 0.1,
    earth_fraction: 0.2, simultaneous_fraction: 0.1,
    longest_darkness_seconds: 7200, longest_earth_outage_seconds: 3600,
    checks: { sunlight: false, earth: false, simultaneous: false },
    explanation: 'Controlled fixture: modeled thresholds not met',
  };
  await page.route('**/api/v1/recommend-sites', route => {
    recommendationRequests.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({ json: {
      api_version: 'v1', start_utc: '2027-11-15T12:00:00Z',
      end_utc: '2027-11-16T12:00:00Z', sampling_seconds: 3600,
      constraints, terrain, candidate_count: 8, requested_recommendations: 5,
      generated_count: 2, evaluated_count: 2, suitable_count: 1,
      unsuitable_count: 1, insufficient_count: 0,
      resolution: 'suitable_candidates',
      candidates: [suitable, unsuitable], recommendations: [suitable],
      dataset_id: 'LOLA-browser-fixture', reference_frame: 'MOON_ME_DE421',
      kernel_manifest_id: 'browser-fixture',
      weights: { sun: 0.4, earth: 0.4, simultaneous: 0.2 },
      screening_scope: 'Controlled DEM-scoped browser fixture',
      fidelity: 'not-scientific-browser-fixture', processing_seconds: 0,
      limitations: ['Controlled UI fixture — not a scientific result'],
    } });
  });

  await page.goto('/');
  const globeCanvas = page.locator('.lunar-canvas canvas').first();
  await expect(globeCanvas).toBeVisible();
  const date = page.getByLabel('Date (UTC)');
  const time = page.getByLabel('Time (UTC)');
  const originalDate = await date.inputValue();
  const originalTime = await time.inputValue();

  await page.getByRole('button', { name: /Recommend landing sites/ }).click();
  await expect(page.getByText('Ranked recommendations')).toBeVisible();
  await expect(page.getByText(/#1 · Score 1\.000/)).toBeVisible();
  await expect(page.getByText(/Evaluated 2 candidates/)).toBeVisible();
  await expect.poll(() => recommendationRequests.length).toBe(1);
  expect(recommendationRequests[0]).toMatchObject({
    start_utc: '2027-11-15T12:00:00Z', duration_hours: 24,
    sampling_seconds: 3600, candidate_count: 8, max_recommendations: 5,
    terrain, constraints,
  });

  await page.getByRole('button', { name: 'Select and analyze site' }).click();
  await expect(page.getByLabel('Latitude (°)')).toHaveValue(String(latitude));
  await expect(page.getByLabel('Longitude (° E)')).toHaveValue(String(longitude));
  await expect(date).toHaveValue(originalDate);
  await expect(time).toHaveValue(originalTime);

  // The Cesium-selected-site display is driven by the same shared state as
  // Mission Controls. This checks the integration, not pixel colors/3D Tiles.
  await expect(globeCanvas).toBeVisible();
  const selected = page.getByText('Selected:', { exact: false });
  await expect(selected).toContainText(`${latitude.toFixed(5)}°`);
  await expect(selected).toContainText(`${longitude.toFixed(5)}° E`);
  await expect.poll(() => siteAnalysisRequests.some(request =>
    request.latitude_deg === latitude && request.longitude_deg === longitude &&
    request.timestamp_utc === '2027-11-15T12:00:00Z')).toBe(true);
  await expect.poll(() => geometryRequests.some(request =>
    request.latitude_deg === latitude && request.longitude_deg === longitude &&
    request.timestamp_utc === '2027-11-15T12:00:00Z')).toBe(true);
  await expect(page.getByText('An error occurred while rendering')).toHaveCount(0);
  await expect(page.getByText('Cesium viewer failed:', { exact: false })).toHaveCount(0);
});
