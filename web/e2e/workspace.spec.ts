import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

const storageKey = 'sccc.scenario.v1';
const blankStyle = {
  version: 8,
  sources: {
    fixture: {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: {},
            geometry: { type: 'Point', coordinates: [151.2093, -33.8688] },
          },
        ],
      },
    },
  },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#e7eee2' } },
    {
      id: 'fixture',
      type: 'circle',
      source: 'fixture',
      paint: { 'circle-radius': 5, 'circle-color': '#527b69' },
    },
  ],
};

async function mapFixtures(page: Page) {
  await page.route('https://api.maptiler.com/**', (route) =>
    route.fulfill(
      route.request().url().includes('logo.svg')
        ? {
            contentType: 'image/svg+xml',
            body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="30"><text y="20">MapTiler</text></svg>',
          }
        : { json: blankStyle },
    ),
  );
}

async function addRental(page: Page, label = 'Eastwood apartment', rent = '720.50') {
  await page.getByRole('button', { name: 'Add a rental' }).click();
  await page.getByLabel('Rental label', { exact: true }).fill(label);
  await page.getByLabel('Weekly rent (AUD)').fill(rent);
  await page.getByLabel('Latitude', { exact: true }).fill('-33.79');
  await page.getByLabel('Longitude', { exact: true }).fill('151.08');
  await page.getByRole('button', { name: 'Save rental', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Selected rental' })).toContainText(label);
}

test.beforeEach(async ({ page }) => {
  await mapFixtures(page);
});

test('real map events, sidebar selection, editing, persistence, export/import and removal', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('.map-surface')).toHaveAttribute('data-map-state', 'ready');
  await expect(page.getByRole('link', { name: 'MapTiler maps' })).toBeVisible();
  await expect(page.getByRole('link', { name: '© OpenStreetMap contributors' })).toBeVisible();

  await page.getByRole('button', { name: 'Set work destination' }).click();
  await page.locator('.maplibregl-canvas').click({ position: { x: 300, y: 240 } });
  await expect(page.getByLabel('Latitude', { exact: true })).not.toHaveValue('');
  await page.getByLabel('Destination label', { exact: true }).fill('City office');
  await page.getByRole('button', { name: 'Save destination', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Work destination: City office' })).toBeVisible();

  await addRental(page);
  await page.getByRole('button', { name: 'Edit rental', exact: true }).click();
  await page.getByLabel('Listing URL').fill('https://example.com/listing');
  await page.getByRole('button', { name: 'Save rental', exact: true }).click();
  await expect(page.getByRole('link', { name: 'View property listing' })).toHaveAttribute(
    'href',
    'https://example.com/listing',
  );
  await addRental(page, 'Ryde unit', '680');
  await page.screenshot({ path: test.info().outputPath('workspace-desktop.png') });
  const firstMarker = page.getByRole('button', {
    name: 'Select rental on map: Eastwood apartment',
    exact: true,
  });
  await firstMarker.focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('button', { name: 'Select rental: Eastwood apartment', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Select rental: Ryde unit', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Select rental on map: Ryde unit', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Edit rental', exact: true }).click();
  await page.getByLabel('Rental label', { exact: true }).fill('Ryde renovated unit');
  await page.getByLabel('Weekly rent (AUD)').fill('695');
  await page.getByRole('button', { name: 'Save rental', exact: true }).click();
  await page.reload();
  await expect(
    page.getByRole('button', { name: 'Select rental: Ryde renovated unit', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('City office', { exact: true })).toBeVisible();

  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export JSON' }).click();
  const download = await downloadEvent;
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream!) chunks.push(chunk);
  const exported = Buffer.concat(chunks).toString('utf8');
  expect(JSON.parse(exported).candidates).toHaveLength(2);
  expect(exported).not.toMatch(/e2e-not-a-real-key|maplibre|maptiler/);

  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Remove rental', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Select rental: Eastwood apartment', exact: true }),
  ).not.toBeVisible();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByLabel('Import workspace file').setInputFiles({
    name: 'workspace.json',
    mimeType: 'application/json',
    buffer: Buffer.from(exported),
  });
  await expect(
    page.getByRole('button', { name: 'Select rental: Eastwood apartment', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('region', { name: 'Selected rental' })).toContainText('$720.50');
  await expect(page.getByRole('region', { name: 'Selected rental' })).toContainText(
    'No journey times or fares are connected yet.',
  );
  await page.getByRole('button', { name: 'Work destination: City office', exact: true }).focus();
  await page.keyboard.press('Enter');
  await page.getByLabel('Destination label', { exact: true }).fill('City office upstairs');
  await page.getByRole('button', { name: 'Save destination', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Work destination: City office upstairs', exact: true }),
  ).toBeVisible();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Remove destination', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Set work destination' })).toBeVisible();
  await expect(page.locator('.map-surface')).toHaveAttribute('data-map-state', 'ready');
  expect(errors).toEqual([]);
});

test('invalid editor and imports never overwrite saved data; cancelling import preserves it', async ({
  page,
}) => {
  await page.goto('/');
  await addRental(page);
  const saved = await page.evaluate((key) => localStorage.getItem(key), storageKey);
  await page.getByRole('button', { name: 'Edit rental', exact: true }).click();
  await page.getByLabel('Weekly rent (AUD)').fill('-2');
  await page.getByRole('button', { name: 'Save rental', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('weekly rent');
  expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toBe(saved);
  for (const body of [
    '{',
    '{"schemaVersion":99}',
    JSON.stringify({ schemaVersion: 1, people: [], destinations: [], candidates: [] }),
  ]) {
    await page.getByLabel('Import workspace file').setInputFiles({
      name: 'invalid.json',
      mimeType: 'application/json',
      buffer: Buffer.from(body),
    });
    await expect(page.getByRole('status').filter({ hasText: 'Import failed:' })).toBeVisible();
    expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toBe(saved);
  }
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByLabel('Import workspace file').setInputFiles({
    name: 'valid.json',
    mimeType: 'application/json',
    buffer: Buffer.from(saved!),
  });
  expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toBe(saved);
});

test('missing key retains accessible editing; corrupted save requires explicit replacement', async ({
  page,
}) => {
  await page.addInitScript((key) => localStorage.setItem(key, 'unreadable original'), storageKey);
  await page.goto('http://127.0.0.1:4174');
  await expect(page.getByRole('heading', { name: 'Your map starts here.' })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('left untouched');
  await addRental(page);
  expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toBe(
    'unreadable original',
  );
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download original save' }).click();
  expect((await downloadEvent).suggestedFilename()).toBe('sccc-unreadable-save.json');
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Replace local save' }).click();
  await expect(page.getByRole('alert')).not.toBeVisible();
  expect(
    JSON.parse((await page.evaluate((key) => localStorage.getItem(key), storageKey))!).candidates,
  ).toHaveLength(1);
});

test('storage unavailable is recoverable and export remains available', async ({ page }) => {
  await page.addInitScript(() =>
    Object.defineProperty(window, 'localStorage', {
      get() {
        throw new Error('blocked');
      },
    }),
  );
  await page.goto('http://127.0.0.1:4174');
  await expect(page.getByRole('alert')).toContainText('storage is unavailable');
  await addRental(page);
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export JSON' }).click();
  expect((await download).suggestedFilename()).toBe('sydney-rental-workspace.json');
});

test('map errors explain provider setup without disabling the shortlist', async ({ page }) => {
  await page.route('https://api.maptiler.com/**', (route) =>
    route.fulfill({ status: 403, body: 'denied' }),
  );
  await page.goto('/');
  await expect(page.getByText(/Map data could not load/)).toBeVisible();
  await addRental(page);
});

test('mobile viewport has no horizontal overflow and all editor actions work', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.locator('.map-surface')).toHaveAttribute('data-map-state', 'ready');
  await addRental(page, '<img src=x onerror=alert(1)>', '700');
  await expect(page.getByRole('region', { name: 'Selected rental' })).toContainText(
    '<img src=x onerror=alert(1)>',
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect
    .poll(async () => {
      const pin = await page
        .getByRole('button', {
          name: 'Select rental on map: <img src=x onerror=alert(1)>',
          exact: true,
        })
        .boundingBox();
      const panel = await page.getByRole('region', { name: 'Selected rental' }).boundingBox();
      return !!pin && !!panel && pin.y + pin.height < panel.y;
    })
    .toBe(true);
  await page.screenshot({ path: test.info().outputPath('workspace-mobile.png'), fullPage: true });
  await page.getByRole('button', { name: 'Edit rental', exact: true }).click();
  await expect(page.getByLabel('Rental label', { exact: true })).toBeVisible();
});
