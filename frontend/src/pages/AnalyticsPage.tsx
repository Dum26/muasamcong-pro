import { AnalyticsTrend, AnalyticsBars } from '../components/shared/AnalyticsCharts';
import './analytics.css';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useEffect, useMemo, useState } from 'react';
import { useConfirm } from '@/components/shared/ConfirmProvider';
import { Link, useSearchParams } from 'react-router';
import { download, post, request } from '../api/client';
import { dateTime, number } from '../lib/format';

interface Metric { tenders: number; priced: number; results: number; investors: number; contractors: number; saving_amount: string | null; saving_rate: string | null }
interface Dimension { value: string; count: number; entity_id?: string }
interface Overview {
  period: string; kpis: Metric; khlcnt: { count: number | null; compatible: boolean };
  changes: number; trend: Array<{ period: string; tenders: number; results: number }>;
  dimensions: Record<string, Dimension[]>;
  source: { last_sync: string | null; tender_count: number; priced_count: number; sync_failures: number };
}
interface Spec { dataset: string; columns: string[]; filters: Array<{ field: string; operator: string; value: string }> }
interface Preview { items: Array<Record<string, string | number | null>>; columns: string[]; total: number; page: number; page_size: number; spec: Spec }
interface Report { id: string; name: string; pinned: boolean; updated_at: string; spec: Spec }
const dimensionNames: Record<string, string> = { location: 'Địa điểm', investor_name: 'Chủ đầu tư', winning_contractor: 'Nhà thầu trúng', status: 'Trạng thái', selection_method: 'Hình thức LCNT', contract_type: 'Loại hợp đồng' };
const columns = ['tender_code', 'title', 'investor_name', 'package_price', 'publish_date'];

export function baseSpec(url: URLSearchParams, extra?: { field: string; value: string }): Spec {
  const filters: Spec['filters'] = [];
  if (url.get('from')) filters.push({ field: 'publish_date', operator: 'after', value: url.get('from')! });
  if (url.get('to')) { const raw = url.get('to')!; const parsed = Date.parse(raw + 'T00:00:00Z');
    filters.push({ field: 'publish_date', operator: 'before', value: Number.isFinite(parsed) ? new Date(parsed + 86_400_000).toISOString().slice(0, 10) : raw }); }
  for (const field of Object.keys(dimensionNames)) if (url.get(field)) filters.push({ field, operator: 'equals', value: url.get(field)! });
  if (extra) filters.push({ field: extra.field, operator: 'equals', value: extra.value });
  return { dataset: 'tenders', columns, filters };
}

export function periodRange(period: string, value: string): [string, string] | null {
  const iso = (date: Date) => date.toISOString().slice(0, 10);
  if (period === 'day' && /^\d{4}-\d{2}-\d{2}$/.test(value)) return [value, value];
  if (period === 'month' && /^\d{4}-\d{2}$/.test(value)) {
    const [year, month] = value.split('-').map(Number);
    return [value + '-01', iso(new Date(Date.UTC(year, month, 0)))];
  }
  if (period === 'year' && /^\d{4}$/.test(value)) return [value + '-01-01', value + '-12-31'];
  if (period === 'quarter' && /^\d{4}-Q[1-4]$/.test(value)) {
    const year = Number(value.slice(0, 4)), quarter = Number(value.at(-1));
    return [iso(new Date(Date.UTC(year, (quarter - 1) * 3, 1))), iso(new Date(Date.UTC(year, quarter * 3, 0)))];
  }
  if (period === 'week' && /^\d{4}-W\d{2}$/.test(value)) {
    const year = Number(value.slice(0, 4)), week = Number(value.slice(6));
    if (week < 1 || week > 53) return null;
    const start = new Date(Date.UTC(year, 0, 4));
    start.setUTCDate(start.getUTCDate() - (start.getUTCDay() || 7) + 1 + (week - 1) * 7);
    const end = new Date(start); end.setUTCDate(start.getUTCDate() + 6);
    return [iso(start), iso(end)];
  }
  return null;
}

export function AnalyticsPage() {
  const confirmAction = useConfirm();
  const [url, setUrl] = useSearchParams();
  const [data, setData] = useState<Overview | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewSpec, setPreviewSpec] = useState<Spec | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const search = url.toString();
  const period = url.get('period') || 'month';
  useEffect(() => { const controller = new AbortController(); setLoading(true); setError('');
    const params = new URLSearchParams(search); if (!params.has('period')) params.set('period', 'month');
    void Promise.all([request<Overview>(`/api/analytics/overview?${params}`, { signal: controller.signal }), request<{ items: Report[] }>('/api/reports', { signal: controller.signal })])
      .then(([overview, saved]) => { setData(overview); setReports(saved.items); }).catch(caught => { if (!controller.signal.aborted) setError(String(caught)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [search, revision]);
  function filter(key: string, value: string) { const next = new URLSearchParams(url); if (value) next.set(key, value); else next.delete(key); setUrl(next, { replace: true }); }
  function selectPeriod(value: string) { const range = periodRange(period, value); if (range) {
    const next = new URLSearchParams(url);
    next.set('from', range[0]); next.set('to', range[1]);
    setUrl(next, { replace: true }); void drill(undefined, undefined, 1, baseSpec(next));
  } }
  async function drill(field?: string, value?: string, page = 1, spec?: Spec) {
    const selected = spec || baseSpec(url, field && value ? { field, value } : undefined);
    setBusy(true); setError('');
    try { setPreview(await post<Preview>('/api/reports/preview', { spec: selected, page, page_size: 25 })); setPreviewSpec(selected); }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }
  async function exportSpec(spec: Spec, reportId = '') {
    setBusy(true); setError('');
    try { await download('/api/reports/export', { spec, format: 'xlsx', ...(reportId ? { report_id: reportId } : {}) }, 'Bao_cao_dau_thau.xlsx'); }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }
  async function reportAction(report: Report, action: 'pin' | 'duplicate' | 'delete') {
    if (action === 'delete' && !await confirmAction(`Xóa báo cáo ${report.name}?`)) return;
    setBusy(true); setError('');
    try { await post(`/api/reports/${report.id}`, { action, pinned: !report.pinned }); setRevision(current => current + 1); }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }
  const cards = useMemo(() => data ? [
    ['TBMT', data.kpis.tenders], ['KHLCNT', data.khlcnt.count], ['Có KQLCNT', data.kpis.results],
    ['Chủ đầu tư', data.kpis.investors], ['Nhà thầu', data.kpis.contractors], ['Có giá', data.kpis.priced],
  ] as const : [], [data]);
  return <main className="page analytics-page"><div className="page-heading"><div><p className="eyebrow">PHÂN TÍCH</p><h1>Phân tích dữ liệu đấu thầu</h1><p>Dữ liệu đã thu thập · cập nhật lần cuối: {dateTime(data?.source.last_sync)}</p></div><div className="form-actions"><Link className="button secondary" to="/app/reports">Báo cáo và dashboard</Link><Button className="secondary" disabled={busy} onClick={() => setRevision(current => current + 1)}>Làm mới</Button></div></div>
    <section className="card"><div className="form-grid"><label>Từ ngày<Input type="date" value={url.get('from') || ''} onChange={event => filter('from', event.target.value)}/></label><label>Đến ngày<Input type="date" value={url.get('to') || ''} onChange={event => filter('to', event.target.value)}/></label><label>Đơn vị thời gian<NativeSelect value={period} onChange={event => filter('period', event.target.value)}><NativeSelectOption value="day">Ngày</NativeSelectOption><NativeSelectOption value="week">Tuần</NativeSelectOption><NativeSelectOption value="month">Tháng</NativeSelectOption><NativeSelectOption value="quarter">Quý</NativeSelectOption><NativeSelectOption value="year">Năm</NativeSelectOption></NativeSelect></label><label>Địa điểm<Input value={url.get('location') || ''} onChange={event => filter('location', event.target.value)}/></label></div><div className="form-actions"><Button className="secondary" onClick={() => setUrl({})}>Xóa bộ lọc</Button><Button onClick={() => void drill()}>Xem dữ liệu nguồn</Button><Button className="secondary" disabled={busy} onClick={() => void exportSpec(baseSpec(url))}>Xuất Excel</Button></div></section>
    {error && <p role="alert" className="error">Không lấy được dữ liệu: {error} <Button className="secondary" onClick={() => setRevision(current => current + 1)}>Thử lại</Button></p>}
    {loading ? <div className="card skeleton"/> : data && <><div className="kpi-grid">{cards.map(([label, value]) => <article className="card" key={label}><span>{label}</span><strong>{value === null ? 'Chưa có dữ liệu' : number(value)}</strong></article>)}</div><section className="card"><h2>Xu hướng gói thầu</h2><AnalyticsTrend items={data.trend} onSelect={selectPeriod}/></section><div className="two-col">{Object.entries(dimensionNames).map(([field, label]) => <section className="card" key={field}><h2>{label}</h2><AnalyticsBars items={data.dimensions[field] || []} label={label} onSelect={value => void drill(field, value)}/></section>)}</div></>}
    {preview && <section className="card"><div className="results-head"><div><h2>Dữ liệu nguồn · {number(preview.total)} dòng</h2><p>Đã áp dụng bộ lọc trên máy chủ.</p></div><Button className="secondary" disabled={busy || !previewSpec} onClick={() => previewSpec && void exportSpec(previewSpec)}>Xuất dữ liệu này</Button></div>{preview.items.length ? <div className="table-scroll"><Table><TableHeader><TableRow>{preview.columns.map(column => <TableHead key={column}>{column}</TableHead>)}</TableRow></TableHeader><TableBody>{preview.items.map((item, index) => <TableRow key={index}>{preview.columns.map(column => <TableCell key={column}>{column === 'tender_code' || column === 'plan_code' ? <Link to={`/app/tenders/${encodeURIComponent(String(item[column] || ''))}`}>{item[column]}</Link> : String(item[column] ?? '—')}</TableCell>)}</TableRow>)}</TableBody></Table></div> : <p className="empty">Không có dòng phù hợp.</p>}<div className="pager"><Button className="secondary" disabled={preview.page <= 1} onClick={() => void drill(undefined, undefined, preview.page - 1, previewSpec!)}>Trước</Button><span>Trang {preview.page} / {Math.max(1, Math.ceil(preview.total / preview.page_size))}</span><Button className="secondary" disabled={preview.page * preview.page_size >= preview.total} onClick={() => void drill(undefined, undefined, preview.page + 1, previewSpec!)}>Sau</Button></div></section>}
    <section className="card"><h2>Báo cáo đã lưu</h2>{reports.length ? <div className="item-list">{reports.map(report => <article className="list-item" key={report.id}><span><strong>{report.pinned ? 'Ghim · ' : ''}{report.name}</strong><small>{report.spec.dataset} · {dateTime(report.updated_at)}</small></span><div className="form-actions"><Button className="secondary" onClick={() => void drill(undefined, undefined, 1, report.spec)}>Chạy</Button><Button className="secondary" onClick={() => void exportSpec(report.spec, report.id)}>Excel</Button><Button className="secondary" onClick={() => void reportAction(report, 'pin')}>{report.pinned ? 'Bỏ ghim' : 'Ghim'}</Button><Button className="secondary" onClick={() => void reportAction(report, 'duplicate')}>Nhân bản</Button><Button className="secondary" onClick={() => void reportAction(report, 'delete')}>Xóa</Button></div></article>)}</div> : <p className="empty">Chưa có báo cáo đã lưu.</p>}</section>
  </main>;
}
