import { describe, expect, it } from 'vitest';
import { searchCellText, searchValidationError, sortableValue } from './SearchPage';
import type { SearchParams, Tender } from '../types';

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

it('distinguishes unfetched KQLCNT from an unavailable winner', () => {
  const row = { winner: '' } as Tender;
  expect(searchCellText(row, 'winner')).toBe('Chưa lấy KQLCNT');
  expect(searchCellText(row, 'winner', true)).toBe('Chưa lấy được tên nhà thầu');
  expect(searchCellText({ ...row, winner: 'Công ty A' }, 'winner', true)).toBe('Công ty A');
});

it('copies the displayed KHLCNT name and preserves empty cells and zero values', () => {
  const row = { package_name: '', plan_name: 'Kế hoạch mua sắm', tender_status: '', package_price: 0 } as unknown as Tender;
  expect(searchCellText(row, 'package_name')).toBe('Kế hoạch mua sắm');
  expect(searchCellText(row, 'tender_status')).toBe('Chưa rõ');
  expect(searchCellText(row, 'investor_name')).toBe('—');
  expect(searchCellText(row, 'package_price')).toBe('0');
});
