export interface Coordinates {
  latitude: number;
  longitude: number;
}

export interface Place {
  id: string;
  label: string;
  coordinates: Coordinates;
}

export interface RentalCandidate extends Place {
  weeklyRentCents: number;
  listingUrl?: string;
}

export interface Scenario {
  schemaVersion: 1;
  people: { id: string; label: string }[];
  destinations: Place[];
  candidates: RentalCandidate[];
}

export const SYDNEY: Coordinates = { latitude: -33.8688, longitude: 151.2093 };
export const MAX_CANDIDATES = 100;
export const MAX_IMPORT_BYTES = 1024 * 1024;
export const MAX_RENT_CENTS = 100_000_000;

export function emptyScenario(): Scenario {
  return {
    schemaVersion: 1,
    people: [{ id: 'traveller-1', label: 'Me' }],
    destinations: [],
    candidates: [],
  };
}

function record(value: unknown, name: string, allowedKeys: string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${name} must be an object.`);
  }
  if (Object.keys(value).some((key) => !allowedKeys.includes(key))) {
    throw new Error(`${name} contains unsupported fields. Export from this version of the app.`);
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, name: string, max = 120): string {
  if (typeof value !== 'string' || !value.trim() || value.length > max) {
    throw new Error(`${name} must contain 1–${max} characters.`);
  }
  return value.trim();
}

export function validateCoordinates(value: unknown): Coordinates {
  const point = record(value, 'Coordinates', ['latitude', 'longitude']);
  for (const [field, limit] of [
    ['latitude', 90],
    ['longitude', 180],
  ] as const) {
    const number = point[field];
    if (typeof number !== 'number' || !Number.isFinite(number) || Math.abs(number) > limit) {
      throw new Error(
        `${field === 'latitude' ? 'Latitude' : 'Longitude'} must be between −${limit} and ${limit}.`,
      );
    }
  }
  return { latitude: point.latitude as number, longitude: point.longitude as number };
}

export function parseCoordinates(latitude: string, longitude: string): Coordinates {
  if (!latitude.trim() || !longitude.trim())
    throw new Error('Enter both latitude and longitude, or choose a point on the map.');
  return validateCoordinates({ latitude: Number(latitude), longitude: Number(longitude) });
}

export function parseRent(value: string): number {
  const input = value.trim();
  if (!/^\d+(?:\.\d{1,2})?$/.test(input))
    throw new Error('Enter weekly rent in AUD, with up to two decimal places.');
  const [dollars, cents = ''] = input.split('.');
  const result = Number(dollars) * 100 + Number(cents.padEnd(2, '0'));
  if (!Number.isSafeInteger(result) || result > MAX_RENT_CENTS)
    throw new Error('Weekly rent must be between $0 and $1,000,000 AUD.');
  return result;
}

export function listingUrl(value: string): string | undefined {
  const input = value.trim();
  if (!input) return undefined;
  if (input.length > 2048) throw new Error('Listing URL is too long.');
  let url: URL;
  try {
    url = new URL(input);
  } catch {
    throw new Error('Listing URL must be a complete http:// or https:// URL.');
  }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new Error('Use an http:// or https:// listing URL without embedded credentials.');
  }
  if (url.href.length > 2048) throw new Error('Listing URL is too long after encoding.');
  return url.href;
}

export function validateScenario(value: unknown): Scenario {
  const source = record(value, 'Scenario', [
    'schemaVersion',
    'people',
    'destinations',
    'candidates',
  ]);
  if (source.schemaVersion !== 1)
    throw new Error('Unsupported scenario version. This app supports schemaVersion 1.');
  if (!Array.isArray(source.people) || source.people.length !== 1)
    throw new Error('This prototype supports one traveller.');
  if (!Array.isArray(source.destinations) || source.destinations.length > 1)
    throw new Error('This prototype supports one work destination.');
  if (!Array.isArray(source.candidates) || source.candidates.length > MAX_CANDIDATES)
    throw new Error(`A workspace supports up to ${MAX_CANDIDATES} rentals.`);
  const ids = new Set<string>();
  function identity(item: Record<string, unknown>, name: string) {
    const id = text(item.id, `${name} ID`, 100);
    if (ids.has(id))
      throw new Error('Every traveller, destination and rental must have a unique ID.');
    ids.add(id);
    return { id, label: text(item.label, `${name} label`) };
  }
  const people = source.people.map((value) =>
    identity(record(value, 'Traveller', ['id', 'label']), 'Traveller'),
  );
  const destinations = source.destinations.map((value) => {
    const item = record(value, 'Destination', ['id', 'label', 'coordinates']);
    return { ...identity(item, 'Destination'), coordinates: validateCoordinates(item.coordinates) };
  });
  const candidates = source.candidates.map((value) => {
    const item = record(value, 'Rental', [
      'id',
      'label',
      'coordinates',
      'weeklyRentCents',
      'listingUrl',
    ]);
    if (
      typeof item.weeklyRentCents !== 'number' ||
      !Number.isSafeInteger(item.weeklyRentCents) ||
      item.weeklyRentCents < 0 ||
      item.weeklyRentCents > MAX_RENT_CENTS
    ) {
      throw new Error('Rental weeklyRentCents must be a whole number from 0 to 100000000.');
    }
    if (item.listingUrl !== undefined && typeof item.listingUrl !== 'string')
      throw new Error('Listing URL must be text.');
    const url = listingUrl((item.listingUrl as string) ?? '');
    return {
      ...identity(item, 'Rental'),
      coordinates: validateCoordinates(item.coordinates),
      weeklyRentCents: item.weeklyRentCents,
      ...(url ? { listingUrl: url } : {}),
    };
  });
  return { schemaVersion: 1, people, destinations, candidates };
}

export function parseScenarioJSON(json: string): Scenario {
  if (new TextEncoder().encode(json).byteLength > MAX_IMPORT_BYTES)
    throw new Error('Scenario file must be 1 MiB or smaller.');
  let value: unknown;
  try {
    value = JSON.parse(json);
  } catch {
    throw new Error('This file is not valid JSON. Your workspace has not changed.');
  }
  return validateScenario(value);
}

export function serializeScenario(scenario: Scenario): string {
  return JSON.stringify(validateScenario(scenario), null, 2) + '\n';
}

export function formatRent(cents: number): string {
  return new Intl.NumberFormat('en-AU', {
    style: 'currency',
    currency: 'AUD',
    maximumFractionDigits: cents % 100 ? 2 : 0,
  }).format(cents / 100);
}
