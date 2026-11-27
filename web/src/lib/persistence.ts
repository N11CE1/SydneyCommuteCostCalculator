import { emptyScenario, parseScenarioJSON, serializeScenario } from './scenario';
import type { Scenario } from './scenario';

export const STORAGE_KEY = 'sccc.scenario.v1';
export type ScenarioStorage = Pick<Storage, 'getItem' | 'setItem'>;

export function loadScenario(getStorage: () => ScenarioStorage): {
  scenario: Scenario;
  error: string | null;
  unreadable?: string;
} {
  let saved: string | null;
  try {
    saved = getStorage().getItem(STORAGE_KEY);
  } catch {
    return {
      scenario: emptyScenario(),
      error: 'Browser storage is unavailable. You can still work and export JSON.',
    };
  }
  if (saved === null) return { scenario: emptyScenario(), error: null };
  try {
    return { scenario: parseScenarioJSON(saved), error: null };
  } catch {
    return {
      scenario: emptyScenario(),
      error:
        'The local save could not be read. It has been left untouched. Download the original before replacing it.',
      unreadable: saved,
    };
  }
}

export function saveScenario(scenario: Scenario, getStorage: () => ScenarioStorage): string | null {
  try {
    getStorage().setItem(STORAGE_KEY, serializeScenario(scenario));
    return null;
  } catch {
    return 'Could not save in this browser. Your current workspace is still here; export JSON to keep it.';
  }
}
