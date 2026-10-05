import { describe, expect, it } from 'vitest';
import { baseSpec, periodRange } from './AnalyticsPage';

describe('analytics drilldown', () => {
  it('keeps the selected date range inclusive for the Python report API', () => {
    const spec = baseSpec(new URLSearchParams('from=2026-09-11&to=2026-09-24'),
      { field: 'location', value: 'Hà Nội' });
    expect(spec.filters).toEqual([
      { field: 'publish_date', operator: 'after', value: '2026-09-11' },
      { field: 'publish_date', operator: 'before', value: '2026-09-25' },
      { field: 'location', operator: 'equals', value: 'Hà Nội' },
    ]);
  });
  it('turns a chart month or ISO week into a date range', () => {
    expect(periodRange('month', '2026-09')).toEqual(['2026-09-01', '2026-09-30']);
    expect(periodRange('week', '2026-W39')).toEqual(['2026-09-21', '2026-09-27']);
  });
});
