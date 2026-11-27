import { describe, expect, it } from 'vitest';
import {
  emptyScenario,
  formatRent,
  listingUrl,
  MAX_CANDIDATES,
  MAX_IMPORT_BYTES,
  parseCoordinates,
  parseRent,
  parseScenarioJSON,
  serializeScenario,
  validateScenario,
} from './scenario';

export function exampleScenario() {
  return {
    ...emptyScenario(),
    destinations: [
      { id: 'work', label: 'Work', coordinates: { latitude: -33.8688, longitude: 151.2093 } },
    ],
    candidates: [
      {
        id: 'home',
        label: 'Eastwood',
        coordinates: { latitude: -33.79, longitude: 151.08 },
        weeklyRentCents: 72050,
        listingUrl: 'https://example.com/rental',
      },
    ],
  };
}

describe('scenario boundary', () => {
  it('round-trips application-owned data with an explicit version', () => {
    const scenario = exampleScenario();
    expect(parseScenarioJSON(serializeScenario(scenario))).toEqual(scenario);
    expect(serializeScenario(scenario)).not.toMatch(/maplibre|marker|apiKey/);
  });
  it('can reimport a maximum-size valid workspace without losing Unicode labels', () => {
    const scenario = exampleScenario();
    scenario.candidates = Array.from({ length: MAX_CANDIDATES }, (_, index) => ({
      ...scenario.candidates[0],
      id: `rental-${index}`,
      label: '🦘'.repeat(60),
      listingUrl: 'https://example.com/' + 'x'.repeat(2000),
    }));
    expect(parseScenarioJSON(serializeScenario(scenario))).toEqual(scenario);
  });
  it('creates independent empty workspaces', () => {
    const first = emptyScenario();
    first.people[0].label = 'Someone else';
    expect(emptyScenario().people[0].label).toBe('Me');
  });
  it.each([
    null,
    [],
    {},
    { ...emptyScenario(), schemaVersion: 2 },
    { ...emptyScenario(), people: [] },
    {
      ...emptyScenario(),
      destinations: [...exampleScenario().destinations, ...exampleScenario().destinations],
    },
    { ...emptyScenario(), candidates: {} },
    {
      ...emptyScenario(),
      candidates: Array(MAX_CANDIDATES + 1).fill(exampleScenario().candidates[0]),
    },
    { ...emptyScenario(), provider: { marker: {} } },
  ])('rejects unsupported or malformed workspace data: %j', (value) => {
    expect(() => validateScenario(value)).toThrow();
  });
  it('rejects duplicate IDs across entity collections', () => {
    const scenario = exampleScenario();
    scenario.candidates[0].id = 'work';
    expect(() => validateScenario(scenario)).toThrow(/unique ID/);
  });
  it.each(['', '   ', 'x'.repeat(121)])('rejects invalid labels', (label) => {
    const scenario = exampleScenario();
    scenario.candidates[0].label = label;
    expect(() => validateScenario(scenario)).toThrow(/label/);
  });
  it('rejects nested provider data instead of persisting it', () => {
    const scenario = exampleScenario();
    Object.assign(scenario.candidates[0].coordinates, { providerObject: {} });
    expect(() => validateScenario(scenario)).toThrow(/unsupported fields/);
  });
  it.each([-1, NaN, Infinity, 0.1, 100_000_001, '72000', null])(
    'rejects invalid rent cents: %s',
    (cents) => {
      const scenario = exampleScenario();
      Object.assign(scenario.candidates[0], { weeklyRentCents: cents });
      expect(() => validateScenario(scenario)).toThrow(/weeklyRentCents/);
    },
  );
  it('rejects non-string listing URLs and unsupported root versions', () => {
    const scenario = exampleScenario();
    Object.assign(scenario.candidates[0], { listingUrl: {} });
    expect(() => validateScenario(scenario)).toThrow(/Listing URL/);
    expect(() => parseScenarioJSON('{"schemaVersion":99}')).toThrow(/version/);
  });
  it('rejects invalid JSON and oversized files before replacement', () => {
    expect(() => parseScenarioJSON('{')).toThrow(/valid JSON/);
    expect(() => parseScenarioJSON(' '.repeat(MAX_IMPORT_BYTES + 1))).toThrow(/smaller/);
    expect(() => parseScenarioJSON('🦘'.repeat(MAX_IMPORT_BYTES / 4 + 1))).toThrow(/smaller/);
  });
});

describe('editor inputs', () => {
  it.each([
    ['720', 72000],
    ['720.50', 72050],
    ['0', 0],
    ['0.01', 1],
    [' 12.5 ', 1250],
    ['1000000', 100000000],
  ])('parses rent %s exactly into cents', (value, expected) => {
    expect(parseRent(value)).toBe(expected);
  });
  it.each([
    '',
    '-1',
    'NaN',
    'Infinity',
    '1e3',
    '$700',
    '700.001',
    '1000000.01',
    '1,000',
    '99999999999999999',
  ])('rejects rent %s', (value) => {
    expect(() => parseRent(value)).toThrow();
  });
  it('validates coordinates, including zero and the geographic limits', () => {
    expect(parseCoordinates('0', '0')).toEqual({ latitude: 0, longitude: 0 });
    expect(parseCoordinates('-90', '180')).toEqual({ latitude: -90, longitude: 180 });
    expect(parseCoordinates('-33.8', '151.1')).toEqual({ latitude: -33.8, longitude: 151.1 });
  });
  it.each([
    ['', '151'],
    [' ', '151'],
    ['-33', ''],
    ['91', '0'],
    ['0', '-181'],
    ['NaN', '0'],
    ['0', 'Infinity'],
  ])('rejects coordinates %s %s', (latitude, longitude) => {
    expect(() => parseCoordinates(latitude, longitude)).toThrow();
  });
  it.each([
    'javascript:alert(1)',
    'data:text/html,hello',
    'file:///tmp/test',
    'not a URL',
    'https://user:pass@example.com',
    'https://example.com/' + 'x'.repeat(2048),
  ])('rejects unsafe listing URL %s', (url) => {
    expect(() => listingUrl(url)).toThrow();
  });
  it('accepts optional links and formats AUD without losing cents', () => {
    expect(listingUrl('  ')).toBeUndefined();
    expect(listingUrl('https://example.com')).toBe('https://example.com/');
    expect(formatRent(72000)).toBe('$720');
    expect(formatRent(72050)).toBe('$720.50');
  });
});
