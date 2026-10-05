import { describe, expect, it } from 'vitest';
import { replayParams } from './HistoryPage';

describe('history replay', () => {
  it('reads the flattened Python history record', () => {
    const params = replayParams({ id: 'one', mode: 'Kế hoạch lựa chọn nhà thầu',
      keyword: 'generic', date_from: '2026-09-11', date_to: '2026-09-24',
      pages: 5, use_dates: true, detail: true, location: 'Hà Nội' });
    expect(params.mode).toBe('Kế hoạch lựa chọn nhà thầu');
    expect(params.keyword).toBe('generic');
    expect(params.date_from).toBe('2026-09-11');
    expect(params.date_to).toBe('2026-09-24');
    expect(params.pages).toBe(5);
    expect(params.location).toBe('Hà Nội');
  });
});
