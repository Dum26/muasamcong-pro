import { describe, expect, it } from 'vitest';
import { searchFromUrl, searchToUrl } from './searchUrl';
import type { SearchParams } from '../types';

const defaults: SearchParams = {
  mode: 'Thông báo mời thầu', keyword: '', use_dates: true,
  date_from: '2026-09-01', date_to: '2026-09-30', status: 'Tất cả trạng thái',
  pages: 2, detail: false, fast_mode: true, remove_duplicates: true,
  bid_form: '', location: '',
};

describe('search URL', () => {
  it('restores every saved filter and page', () => {
    const saved = { ...defaults, mode: 'Kế hoạch lựa chọn nhà thầu' as const,
      keyword: 'thuốc generic', use_dates: false, status: 'Đã đóng thầu', pages: 5,
      detail: true, fast_mode: false, remove_duplicates: false,
      bid_form: 'Đấu thầu rộng rãi', location: 'Hà Nội' };
    const url = searchToUrl(saved, 3);
    expect(searchFromUrl(url, defaults)).toEqual(saved);
    expect(url.get('page')).toBe('3');
  });

  it('ignores invalid page count from the URL', () => {
    expect(searchFromUrl(new URLSearchParams('pages=999'), defaults).pages).toBe(2);
  });
});
