import { expect, test, type Page } from '@playwright/test';

// These are explicit browser fixtures; they do NOT assert scientific ephemerides.
async function fixture(page: Page) {
  await page.route('**/api/v1/health', route => route.fulfill({ json: {
    status: 'ok', api_version: 'v1', science_available: true, detail: 'Controlled UI fixture',
  } }));
  await page.route('**/api/v1/metadata', route => route.fulfill({ json: {
    api_version: 'v1', modes: ['geometric','terrain_aware'], supported_targets: ['SUN','EARTH'],
    reference_frame: 'MOON_ME_DE421', coordinate_convention: 'Planetocentric; east-positive',
    terrain_dataset_id: null, terrain_configured: false, kernel_manifests_configured: true,
    max_timeline_samples: 2048, max_timeline_days: 90, limitations: ['Browser test fixture'],
  } }));
  await page.route('**/api/v1/geometry', async route => {
    const payload = route.request().postDataJSON() as { latitude_deg: number; longitude_deg: number; timestamp_utc: string };
    await route.fulfill({ json: {
      ...payload, observer_height_m: 2, observer_reference_elevation_m: 0,
      sun: { body: 'SUN', azimuth_deg: null, elevation_deg: 90,
        east_unit: 0, north_unit: 0, up_unit: 1, range_km: 1e8,
        position_moon_fixed_km: [0,0,0], geometric_visibility: 'visible' },
      earth: { body: 'EARTH', azimuth_deg: 0, elevation_deg: -90,
        east_unit: 0, north_unit: 0, up_unit: -1, range_km: 400000,
        position_moon_fixed_km: [0,0,0], geometric_visibility: 'obstructed' },
      metadata: { api_version: 'v1', reference_frame: 'MOON_ME_DE421', kernel_manifest_id: 'controlled-UI-fixture',
        terrain_dataset_id: null, mode: 'geometry', aberration: 'NONE', fidelity: 'test-fixture',
        limitations: ['Not real science'], latitude_type: 'planetocentric', longitude_positive: 'east',
        angular_unit: 'deg', horizontal_distance_unit: 'km', height_unit: 'm' },
    } });
  });
  await page.route('**/api/v1/terrain/mesh*', route => route.fulfill({ json: {
    status: 'complete', coordinate_frame: 'local_east_up_north',
    latitude_deg: -89.5, longitude_deg: 45, center_elevation_m: -393.18,
    radius_m: 160, sample_step_m: 320, grid_side: 2, valid_samples: 4, requested_samples: 4,
    vertices: [[-160, 0, 160], [160, 12, 160], [-160, -4, -160], [160, 8, -160]],
    indices: [0, 1, 2, 1, 3, 2], metadata: { dataset_id: 'LOLA-browser-fixture',
      coordinate_frame: 'local_east_up_north', vertical_exaggeration: 1, center_is_local_origin: true,
      datum_confirmed: true, visual_only: true, pixel_size_m: 80, reference_frame: 'MOON_ME_DE421',
      frame_alignment_note: 'fixture only' },
  } }));
  await page.route('**/api/v1/site-analysis', route => route.fulfill({
    status: 422, json: { code: 'terrain_coverage_error', detail: 'Controlled UI fixture: unavailable terrain' },
  }));
}

test.beforeEach(async ({ page }) => { await fixture(page); });

test('Babylon view initializes, has usable canvas, updates lighting and preserves Cesium navigation on return', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.lunar-canvas canvas').first()).toBeVisible();
  await page.getByRole('button', { name: 'Local surface · Babylon' }).click();
  const canvas = page.getByLabel('Babylon local lunar surface canvas');
  await expect(canvas).toBeVisible();
  await expect(page.getByTestId('local-terrain-status')).toContainText('NASA LOLA terrain loaded');
  await expect(page.getByText('WebGL or terrain rendering unavailable:', { exact: false })).toHaveCount(0);
  await page.getByRole('button', { name: 'Analyze site' }).click();
  await expect(page.getByTestId('local-solar-status')).toContainText('Scientific Sun direction loaded');
  const date = page.getByLabel('Date (UTC)');
  await date.fill('2027-11-16');
  await expect(page.getByTestId('local-solar-status')).toContainText('Scientific Sun direction loaded');
  await expect(page.getByText('2027-11-16T12:00:00Z', { exact: false }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Global Moon · Cesium' }).click();
  await expect(page.locator('.lunar-canvas canvas').first()).toBeVisible();
  await expect(page.getByText('An error occurred while rendering')).toHaveCount(0);
  await page.getByRole('button', { name: 'Local surface · Babylon' }).click();
  await expect(page.getByLabel('Babylon local lunar surface canvas')).toBeVisible();
});

test('unavailable scientific data leaves Babylon directional sunlight disabled', async ({ page }) => {
  await page.route('**/api/v1/geometry', route => route.fulfill({
    status: 503, json: { code: 'scientific_data_unavailable', detail: 'Controlled fixture: kernels missing' },
  }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Local surface · Babylon' }).click();
  await page.getByRole('button', { name: 'Analyze site' }).click();
  await expect(page.getByTestId('local-solar-status')).toContainText('scientific geometry unavailable', { ignoreCase: true });
  await expect(page.getByTestId('local-solar-status')).not.toContainText('Scientific Sun direction loaded');
});

test('unsupported landing site never shows a fabricated local terrain mesh', async ({ page }) => {
  await page.route('**/api/v1/terrain/mesh*', route => route.fulfill({
    status: 422, json: { code: 'outside_coverage', detail: 'Site outside DEM' },
  }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Local surface · Babylon' }).click();
  await expect(page.getByTestId('local-terrain-status')).toContainText('outside the configured NASA LOLA DEM coverage');
  await expect(page.getByTestId('local-terrain-provenance')).toHaveCount(0);
});
