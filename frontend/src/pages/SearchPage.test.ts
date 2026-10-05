import { describe, expect, it } from 'vitest';
import { searchValidationError, sortableValue } from './SearchPage';
import type { SearchParams } from '../types';

describe('search result sorting', () => {
  it('orders Vietnamese publication dates chronologically', () => {
    const dates = ['24/09/2026 17:10', '11/09/2026 08:00', '13/09/2026 09:00'];
    expect(dates.sort((a, b) => sortableValue(a, 'public_date').localeCompare(sortableValue(b, 'public_date'))))
      .toEqual(['11/09/2026 08:00', '13/09/2026 09:00', '24/09/2026 17:10']);
  });
});

describe('search form validation', () => {
  const valid = { keyword: 'generic', use_dates: true, date_from: '2026-09-11', date_to: '2026-09-24', pages: 2 } as SearchParams;
  it('rejects a reversed date range before starting the API job', () => {
    expect(searchValidationError({ ...valid, date_from: '2026-09-25' })).toMatch(/ngày bắt đầu/);
    expect(searchValidationError(valid)).toBe('');
  });
});
