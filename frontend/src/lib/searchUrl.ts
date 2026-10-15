import type { SearchParams } from '../types';

export function searchFromUrl(url: URLSearchParams, defaults: SearchParams): SearchParams {
  const pages = Number(url.get('pages'));
  return {
    ...defaults,
    mode: url.get('mode') === 'Kế hoạch lựa chọn nhà thầu' ? 'Kế hoạch lựa chọn nhà thầu' : defaults.mode,
    keyword: url.get('q') || '',
    use_dates: url.get('dates') !== '0',
    date_from: url.get('from') || defaults.date_from,
    date_to: url.get('to') || defaults.date_to,
    status: url.get('status') || defaults.status,
    pages: Number.isInteger(pages) && pages >= 1 && pages <= 30 ? pages : defaults.pages,
    detail: url.has('detail') ? url.get('detail') === '1' : defaults.detail,
    fast_mode: url.has('fast') ? url.get('fast') !== '0' : defaults.fast_mode,
    remove_duplicates: url.get('dedup') !== '0',
    bid_form: url.get('bid_form') || '',
    location: url.get('location') || '',
  };
}

export function searchToUrl(params: SearchParams, page = 1): URLSearchParams {
  const url = new URLSearchParams();
  if (params.mode !== 'Thông báo mời thầu') url.set('mode', params.mode);
  if (params.keyword) url.set('q', params.keyword);
  if (!params.use_dates) url.set('dates', '0');
  if (params.date_from) url.set('from', params.date_from);
  if (params.date_to) url.set('to', params.date_to);
  if (params.status !== 'Tất cả trạng thái') url.set('status', params.status);
  if (params.pages !== 2) url.set('pages', String(params.pages));
  url.set('detail', params.detail ? '1' : '0');
  url.set('fast', params.fast_mode ? '1' : '0');
  if (!params.remove_duplicates) url.set('dedup', '0');
  if (params.bid_form) url.set('bid_form', params.bid_form);
  if (params.location) url.set('location', params.location);
  if (page > 1) url.set('page', String(page));
  return url;
}
