import { expect, test, type Page } from '@playwright/test';

// Browser interaction fixtures are intentionally not astronomical data.
// The test API returns explicit unavailability errors. Real SPICE/LOLA
// numerical correctness remains covered by the separate backend tests.
async function stubScienceUnavailable(page: Page) {
  await page.route('**/api/v1/health', route => route.fulfill({
    json: { status: 'ok', api_version: 'v1', science_available: false, detail: 'E2E fixture: no scientific kernels' },
  }));
  await page.route('**/api/v1/metadata', route => route.fulfill({
    json: {
      api_version: 'v1', modes: ['geometric', 'terrain_aware'], supported_targets: ['SUN', 'EARTH'],
      reference_frame: 'MOON_ME_DE421', coordinate_convention: 'Planetocentric latitude; east-positive longitude',
      terrain_dataset_id: null, terrain_configured: false, kernel_manifests_configured: false,
      max_timeline_samples: 2048, max_timeline_days: 90, limitations: ['E2E test fixture; no science'],
    },
  }));
  await page.route('**/api/v1/geometry', route => route.fulfill({
    status: 503, json: { code: 'scientific_data_unavailable', detail: 'E2E fixture: no scientific calculations' },
  }));
  await page.route('**/api/v1/site-analysis', route => route.fulfill({
    status: 422, json: { code: 'terrain_coverage_error', detail: 'E2E fixture: no DEM coverage' },
  }));
}

async function assertNoCesiumCrash(page: Page) {
  await expect(page.getByText('An error occurred while rendering')).toHaveCount(0);
  await expect(page.getByText('normalized result is not a number')).toHaveCount(0);
  await expect(page.getByText('Cesium viewer failed:', { exact: false })).toHaveCount(0);
}

test.beforeEach(async ({ page }) => {
  await stubScienceUnavailable(page);
});

test('renders Moon, has a canvas, and supports camera drag/zoom without a Cesium crash', async ({ page }) => {
  await page.goto('/');
  const canvas = page.locator('.lunar-canvas canvas').first();
  await expect(canvas).toBeVisible();
  await expect(page.getByText('CESIUM · LUNAR REFERENCE SPHERE')).toBeVisible();
  await expect(page.getByText('Visualization fallback:', { exact: false })).toBeVisible();
  await page.waitForTimeout(1500); // Allow Cesium its first render cycle.
  await assertNoCesiumCrash(page);
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  const x = box!.x + box!.width * 0.5;
  const y = box!.y + box!.height * 0.5;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 70, y + 30, { steps: 8 });
  await page.mouse.up();
  await page.mouse.wheel(0, -250);
  await page.waitForTimeout(800);
  await assertNoCesiumCrash(page);
});

test('globe click updates coordinates, preserves UTC, places marker and dispatches unchanged scientific request', async ({ page }) => {
  const geometryRequests: Array<Record<string, unknown>> = [];
  const siteRequests: Array<Record<string, unknown>> = [];
  page.on('request', req => {
    if (req.method() !== 'POST') return;
    const body = req.postDataJSON() as Record<string, unknown>;
    if (req.url().endsWith('/api/v1/geometry')) geometryRequests.push(body);
    if (req.url().endsWith('/api/v1/site-analysis')) siteRequests.push(body);
  });
  await page.goto('/');
  const canvas = page.locator('.lunar-canvas canvas').first();
  await expect(canvas).toBeVisible();
  const lat = page.getByLabel('Latitude (°)');
  const lon = page.getByLabel('Longitude (° E)');
  const utcDate = page.getByLabel('Date (UTC)');
  const utcTime = page.getByLabel('Time (UTC)');
  const beforeDate = await utcDate.inputValue();
  const beforeTime = await utcTime.inputValue();
  const previousLat = await lat.inputValue();
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  // Click inside the visible disk, away from its centered selected-site label.
  await canvas.click({ position: { x: box!.width * 0.62, y: box!.height * 0.44 } });
  await expect.poll(() => lat.inputValue()).not.toBe(previousLat);
  const chosenLat = Number(await lat.inputValue());
  const chosenLon = Number(await lon.inputValue());
  expect(chosenLat).toBeGreaterThanOrEqual(-90);
  expect(chosenLat).toBeLessThanOrEqual(90);
  expect(chosenLon).toBeGreaterThanOrEqual(-180);
  expect(chosenLon).toBeLessThan(180);
  await expect(page.getByText('Selected:', { exact: false })).toContainText(chosenLat.toFixed(5));
  await expect(utcDate).toHaveValue(beforeDate);
  await expect(utcTime).toHaveValue(beforeTime);
  await expect.poll(() => siteRequests.length).toBeGreaterThan(0);
  await expect.poll(() => geometryRequests.length).toBeGreaterThan(0);
  const site = siteRequests.at(-1)!;
  const geometry = geometryRequests.at(-1)!;
  expect(Number(site.latitude_deg)).toBeCloseTo(chosenLat, 8);
  expect(Number(site.longitude_deg)).toBeCloseTo(chosenLon, 8);
  expect(site.timestamp_utc).toBe('2027-11-15T12:00:00Z');
  expect(geometry.timestamp_utc).toBe(site.timestamp_utc);
  await expect(page.getByText('E2E fixture: no DEM coverage', { exact: false })).toBeVisible();
  await assertNoCesiumCrash(page);
});

test('manual Mission Controls changes update selected marker and focus stays stable at poles', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.lunar-canvas canvas').first()).toBeVisible();
  await page.getByLabel('Latitude (°)').fill('-85');
  await page.getByLabel('Longitude (° E)').fill('30');
  await expect(page.getByText('Selected:', { exact: false })).toContainText('-85.00000°');
  await expect(page.getByText('Selected:', { exact: false })).toContainText('30.00000°');
  await page.getByRole('button', { name: 'Focus site' }).click();
  await page.waitForTimeout(1500);
  await assertNoCesiumCrash(page);
  for (const pole of ['-90', '90']) {
    await page.getByLabel('Latitude (°)').fill(pole);
    await page.getByLabel('Longitude (° E)').fill('45');
    await expect(page.getByText('Selected:', { exact: false })).toContainText('0.00000° E');
    await page.getByRole('button', { name: 'Focus site' }).click();
    await page.waitForTimeout(1400);
    await assertNoCesiumCrash(page);
  }
});
