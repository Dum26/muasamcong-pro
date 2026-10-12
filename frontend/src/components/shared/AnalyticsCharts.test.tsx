import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AnalyticsBars, AnalyticsTrend } from './AnalyticsCharts';

describe('analytics charts', () => {
  it('renders zero values and both trend series without invalid coordinates', () => {
    const markup = renderToStaticMarkup(<AnalyticsTrend items={[{ period: '2026-10', tenders: 0, results: 0 }]} onSelect={() => {}}/>);
    expect(markup).not.toMatch(/NaN|Infinity/);
    expect(markup).toContain('analytics-result-line');
    expect(markup).toContain('tabindex="0"');
    expect(markup).toContain('2026-10');
  });
  it('keeps all dimension names available when the chart displays the top ten', () => {
    const markup = renderToStaticMarkup(<AnalyticsBars items={Array.from({ length: 12 }, (_, index) => ({ value: `Investor ${index}`, count: 0 }))} label="Chủ đầu tư" onSelect={() => {}}/>);
    expect(markup).not.toMatch(/NaN|Infinity/);
    expect(markup.match(/class="analytics-bar"/g)).toHaveLength(10);
    expect(markup).toContain('Investor 11');
  });
  it('shows an empty state instead of inventing chart data', () => {
    expect(renderToStaticMarkup(<AnalyticsTrend items={[]} onSelect={() => {}}/>)).toContain('Chưa có dữ liệu');
    expect(renderToStaticMarkup(<AnalyticsBars items={[]} label="Địa điểm" onSelect={() => {}}/>)).toContain('Chưa có dữ liệu');
  });
});
