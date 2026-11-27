import { describe, expect, it, vi } from 'vitest';
import { loadScenario, saveScenario, STORAGE_KEY } from './persistence';
import { emptyScenario, serializeScenario } from './scenario';

function storage(saved: string | null = null) {
  return { getItem: vi.fn(() => saved), setItem: vi.fn() };
}

describe('browser persistence', () => {
  it('starts empty on first visit without writing anything', () => {
    const store = storage();
    expect(loadScenario(() => store)).toEqual({ scenario: emptyScenario(), error: null });
    expect(store.getItem).toHaveBeenCalledWith(STORAGE_KEY);
    expect(store.setItem).not.toHaveBeenCalled();
  });
  it('loads validated data', () => {
    const scenario = emptyScenario();
    expect(loadScenario(() => storage(serializeScenario(scenario)))).toEqual({
      scenario,
      error: null,
    });
  });
  it.each(['{', '{"schemaVersion":99}', '{}'])(
    'preserves unreadable local data for recovery',
    (raw) => {
      const store = storage(raw);
      const result = loadScenario(() => store);
      expect(result.error).toMatch(/left untouched/);
      expect(result.unreadable).toBe(raw);
      expect(store.setItem).not.toHaveBeenCalled();
    },
  );
  it('handles blocked storage access without crashing', () => {
    const blocked = () => {
      throw new Error('denied');
    };
    expect(loadScenario(blocked).error).toMatch(/unavailable/);
    expect(saveScenario(emptyScenario(), blocked)).toMatch(/Could not save/);
  });
  it('reports quota failures and saves only validated plain data', () => {
    const store = storage();
    expect(saveScenario(emptyScenario(), () => store)).toBeNull();
    expect(store.setItem).toHaveBeenCalledWith(STORAGE_KEY, serializeScenario(emptyScenario()));
    store.setItem.mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });
    expect(saveScenario(emptyScenario(), () => store)).toMatch(/export JSON/);
  });
});
