import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router';
import { searchApi, workspaceApi } from '../api/core';
import { ApiError } from '../api/client';
import { request } from '../api/client';
import { tenderCode } from '../lib/format';
import { searchFromUrl, searchToUrl } from '../lib/searchUrl';
import type { SavedSearch, SearchParams, Tender, WatchItem } from '../types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Columns3, Copy, MoreHorizontal, Search, Star, X } from 'lucide-react';
import { Pagination } from '@/components/data-table/Pagination';
import { EmptyState } from '@/components/shared/EmptyState';
import { toast } from 'sonner';

const today = new Date();
const iso = (date: Date) => date.toISOString().slice(0, 10);
const defaults: SearchParams = { mode: 'Thông báo mời thầu', keyword: '', use_dates: true,
  date_from: iso(new Date(today.getFullYear(), today.getMonth(), 1)), date_to: iso(today),
  status: 'Tất cả trạng thái', pages: 2, detail: false, fast_mode: true,
  remove_duplicates: true, bid_form: '', location: '' };
const columns: Array<[keyof Tender, string]> = [
  ['notify_no', 'Mã TBMT / KHLCNT'], ['package_name', 'Tên gói thầu'],
  ['investor_name', 'Chủ đầu tư'], ['package_price', 'Giá gói thầu'],
  ['public_date', 'Ngày đăng'], ['bid_close_date', 'Đóng thầu'],
  ['tender_status', 'Trạng thái'], ['winner', 'KQLCNT'],
];
export function searchCellText(row: Tender, key: keyof Tender): string {
  if (key === 'notify_no') return tenderCode(row);
  if (key === 'package_name') return row.package_name || row.plan_name || '—';
  if (key === 'tender_status') return row.tender_status || 'Chưa rõ';
  return String(row[key] ?? '') || '—';
}
export function sortableValue(value: unknown, key: keyof Tender): string {
  const raw = String(value ?? '').trim();
  if (key === 'public_date' || key === 'bid_close_date') {
    const match = raw.match(/^(\d{2})\/(\d{2})\/(\d{4})(.*)$/);
    return match ? `${match[3]}-${match[2]}-${match[1]}${match[4]}` : raw;
  }
  return raw;
}
export function searchValidationError(params: SearchParams): string {
  if (!params.keyword.trim() && !params.use_dates) return 'Hãy nhập từ khóa hoặc bật lọc ngày.';
  if (params.use_dates && (!params.date_from || !params.date_to || params.date_from > params.date_to)) return 'Chọn khoảng ngày hợp lệ: ngày bắt đầu không sau ngày kết thúc.';
  if (!Number.isInteger(params.pages) || params.pages < 1 || params.pages > 30) return 'Số trang nguồn phải từ 1 đến 30.';
  return '';
}

export function SearchPage() {
  const [url, setUrl] = useSearchParams();
  const [form, setForm] = useState<SearchParams>(() => searchFromUrl(url, defaults));
  const [rows, setRows] = useState<Tender[]>([]); const [jobId, setJobId] = useState('');
  const [phase, setPhase] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');
  const [message, setMessage] = useState(''); const [error, setError] = useState('');
  const [page, setPage] = useState(() => Math.max(1, Number(url.get('page')) || 1)); const [sort, setSort] = useState<keyof Tender>('public_date');
  const [descending, setDescending] = useState(false); const [selected, setSelected] = useState<Set<number>>(new Set());
  const [presets, setPresets] = useState<SavedSearch[]>([]); const [watchlist, setWatchlist] = useState<WatchItem[]>([]);
  const [busy, setBusy] = useState(false); const run = useRef(0); const activeRequest = useRef<AbortController | null>(null);
  const [nameDialog, setNameDialog] = useState<{ mode: 'save' | 'rename'; item?: SavedSearch } | null>(null);
  const [presetName, setPresetName] = useState('');
  const [deletePreset, setDeletePreset] = useState<SavedSearch | null>(null);
  const [suggestions, setSuggestions] = useState<Array<{ code: string; name: string; kind: string }>>([]);
  const [visibleKeys, setVisibleKeys] = useState<Set<keyof Tender>>(() => {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem('msc_search_columns') || 'null');
      if (Array.isArray(saved)) {
        const keys = columns.map(([key]) => key).filter(key => saved.includes(key));
        if (keys.length) return new Set(keys);
      }
    } catch { /* Ignore an invalid local preference. */ }
    return new Set(columns.map(([key]) => key));
  });
  useEffect(() => { const query = form.keyword.trim(); if (query.length < 2) { setSuggestions([]); return; }
    const controller = new AbortController(); const timer = window.setTimeout(() => {
      void request<{ items: Array<{ code: string; name: string; kind: string }> }>('/api/intelligence/suggest?q=' + encodeURIComponent(query), { signal: controller.signal })
        .then(result => setSuggestions(result.items)).catch(() => { if (!controller.signal.aborted) setSuggestions([]); });
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [form.keyword]);
  useEffect(() => { void Promise.all([workspaceApi.presets(), workspaceApi.watchlist()]).then(([saved, watched]) => { setPresets(saved.presets); setWatchlist(watched.items); }).catch(() => {}); }, []);
  useEffect(() => { setForm(searchFromUrl(url, defaults)); setPage(Math.max(1, Number(url.get('page')) || 1)); }, [url]);
  useEffect(() => { if (url.get('run') !== '1') return;
    const timer = window.setTimeout(() => void start(undefined, searchFromUrl(url, defaults)), 0);
    return () => window.clearTimeout(timer);
  }, [url]);
  useEffect(() => () => { run.current++; activeRequest.current?.abort(); }, []);
  function applyForm(next: SearchParams) { setForm(next); setPage(1); setUrl(searchToUrl(next), { replace: true }); }
  function field<K extends keyof SearchParams>(key: K, value: SearchParams[K]) { applyForm({ ...form, [key]: value }); }
  function changePage(next: number) { setPage(next); setUrl(searchToUrl(form, next), { replace: true }); }
  async function start(event?: FormEvent, params: SearchParams = form) {
    event?.preventDefault();
    const invalid = searchValidationError(params);
    if (invalid) { setError(invalid); return; }
    activeRequest.current?.abort();
    const controller = new AbortController(); activeRequest.current = controller;
    const current = ++run.current; setPhase('loading'); setError(''); setMessage('Đang khởi tạo truy vấn…');
    setRows([]); setSelected(new Set()); setPage(1); setJobId('');
    setUrl(searchToUrl(params), { replace: true });
    try {
      const job = await searchApi.start(params, controller.signal); if (current !== run.current) return;
      setJobId(job.id);
      void workspaceApi.historyAction({ params }).catch(() => {});
      while (current === run.current) {
        const currentJob = await searchApi.poll(job.id, controller.signal);
        if (current !== run.current) return;
        setMessage(currentJob.message);
        if (currentJob.state === 'error') throw new Error(currentJob.error || currentJob.message);
        if (currentJob.state === 'done') {
          setRows(currentJob.rows || []); setPhase('done');
          void workspaceApi.historyAction({ action: 'complete', params, result_count: currentJob.source_count }).catch(() => {});
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 650));
      }
    } catch (caught) { if (current === run.current) { setError(caught instanceof Error ? caught.message : 'Không lấy được dữ liệu.'); setPhase('error'); } }
    finally { if (activeRequest.current === controller) activeRequest.current = null; }
  }
  const filtered = useMemo(() => rows.filter(row =>
    (!form.location || row.location.toLocaleLowerCase('vi').includes(form.location.toLocaleLowerCase('vi'))) &&
    (!form.bid_form || row.bid_form.toLocaleLowerCase('vi').includes(form.bid_form.toLocaleLowerCase('vi')))), [rows, form.location, form.bid_form]);
  const ordered = useMemo(() => [...filtered].sort((a, b) => sortableValue(a[sort], sort).localeCompare(sortableValue(b[sort], sort), 'vi', { numeric: true }) * (descending ? -1 : 1)), [filtered, sort, descending]);
  const shown = ordered.slice((page - 1) * 50, page * 50);
  const compareCodes = rows.filter(row => selected.has(row.index)).map(tenderCode).filter(code => code.startsWith('IB'));
  async function savePreset(name: string) {
    try { setPresets((await workspaceApi.presetAction({ action: 'save', name, params: form })).presets); setNameDialog(null); toast.success('Đã lưu bộ lọc.'); }
    catch (caught) { setError(String(caught)); toast.error(String(caught)); }
  }
  async function presetAction(item: SavedSearch, action: 'rename' | 'pin' | 'watch' | 'delete', name?: string) {
    try { setPresets((await workspaceApi.presetAction({ action, id: item.id, name, pinned: !item.pinned, enabled: !item.is_watch_enabled })).presets); setNameDialog(null); setDeletePreset(null); }
    catch (caught) { setError(String(caught)); toast.error(String(caught)); }
  }
  async function toggleWatch(row: Tender) {
    const code = tenderCode(row); const exists = watchlist.some(item => item.code === code);
    try { setWatchlist((await workspaceApi.watch({ action: exists ? 'remove' : 'add', code,
      name: row.package_name || row.plan_name, investor: row.investor_name,
      deadline: row.bid_close_date, url: row.source_url, row })).items); toast.success(exists ? 'Đã bỏ theo dõi.' : 'Đã theo dõi gói thầu.'); }
    catch (caught) { const message = caught instanceof Error ? caught.message : 'Không cập nhật được theo dõi.'; setError(message); toast.error(message); }
  }
  async function exportRows(all = false) {
    if (!jobId) return; setBusy(true); setError('');
    try { await searchApi.export(jobId, all ? undefined : [...selected]); }
    catch (caught) { setError(caught instanceof ApiError ? `${caught.message} ${caught.requestId || ''}` : String(caught)); }
    finally { setBusy(false); }
  }
  async function copyColumn(key: keyof Tender) {
    const values = ordered.map(row => searchCellText(row, key)).map(value => value.replace(/[\t\r\n]+/g, ' '));
    try { await navigator.clipboard.writeText(values.join('\n')); setMessage(`Đã sao chép ${values.length} ô trong cột.`); toast.success(`Đã sao chép ${values.length} ô.`); }
    catch { setError('Không sao chép được. Hãy cấp quyền clipboard cho trình duyệt.'); }
  }
  function toggleColumn(key: keyof Tender) {
    const next = new Set(visibleKeys);
    if (next.has(key) && next.size > 1) next.delete(key); else next.add(key);
    setVisibleKeys(next); localStorage.setItem('msc_search_columns', JSON.stringify([...next]));
  }
  const activeFilters = [
    form.keyword.trim() && { label: `Từ khóa: ${form.keyword.trim()}`, clear: () => field('keyword', '') },
    form.use_dates && { label: `${form.date_from} → ${form.date_to}`, clear: () => field('use_dates', false) },
    form.status !== defaults.status && { label: `Trạng thái: ${form.status}`, clear: () => field('status', defaults.status) },
    form.location && { label: `Địa điểm: ${form.location}`, clear: () => field('location', '') },
    form.bid_form && { label: `Hình thức: ${form.bid_form}`, clear: () => field('bid_form', '') },
  ].filter((item): item is { label: string; clear: () => void } => Boolean(item));
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">TRA CỨU E-GP</p><h1>Tra cứu dữ liệu đấu thầu</h1><p>Tìm TBMT và KHLCNT, theo dõi gói và xuất kết quả.</p></div></div>
    <form className="card search-form" onSubmit={event => void start(event)}>
      <div className="form-grid">
        <label>Loại dữ liệu<NativeSelect value={form.mode} onChange={event => field('mode', event.target.value as SearchParams['mode'])}><NativeSelectOption>Thông báo mời thầu</NativeSelectOption><NativeSelectOption>Kế hoạch lựa chọn nhà thầu</NativeSelectOption></NativeSelect></label>
        <div className="wide grid gap-1.5"><label htmlFor="search-keyword">Từ khóa, mã hoặc tên gói</label><div className="relative"><Search size={16} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"/><Input id="search-keyword" className="pl-9 pr-9" list="search-suggestions" value={form.keyword} onChange={event => field('keyword', event.target.value)} placeholder="Ví dụ: generic, IB2600…, PL2600…"/>{form.keyword && <Button type="button" variant="ghost" size="icon-xs" className="absolute right-2 top-1/2 -translate-y-1/2" aria-label="Xóa từ khóa" onClick={() => field('keyword', '')}><X size={14}/></Button>}</div><datalist id="search-suggestions">{suggestions.map(item => <NativeSelectOption key={`${item.kind}-${item.code}`} value={item.code} label={item.name}/>)}</datalist></div>
        <label>Trạng thái<Input value={form.status} onChange={event => field('status', event.target.value)}/></label>
        <label>Từ ngày<Input type="date" disabled={!form.use_dates} value={form.date_from} onChange={event => field('date_from', event.target.value)}/></label>
        <label>Đến ngày<Input type="date" disabled={!form.use_dates} value={form.date_to} onChange={event => field('date_to', event.target.value)}/></label>
        <label>Số trang nguồn<Input type="number" min="1" max="30" value={form.pages} onChange={event => field('pages', Number(event.target.value))}/></label>
        <label>Địa điểm (lọc bảng)<Input value={form.location} onChange={event => field('location', event.target.value)}/></label>
        <label>Hình thức LCNT (lọc bảng)<Input value={form.bid_form} onChange={event => field('bid_form', event.target.value)}/></label>
      </div>
      {form.use_dates && (!form.date_from || !form.date_to || form.date_from > form.date_to) && <p role="alert" className="error mt-2">Chọn khoảng ngày hợp lệ: ngày bắt đầu không sau ngày kết thúc.</p>}
      <div className="form-actions">
        <label className="check"><Checkbox checked={form.use_dates} onCheckedChange={checked => field('use_dates', checked === true)}/> Lọc theo ngày</label>
        <label className="check"><Checkbox checked={form.detail} onCheckedChange={checked => field('detail', checked === true)}/> Lấy chi tiết</label>
        <label className="check"><Checkbox checked={form.remove_duplicates} onCheckedChange={checked => field('remove_duplicates', checked === true)}/> Bỏ trùng</label>
        <Button disabled={phase === 'loading' || !!searchValidationError(form)}>{phase === 'loading' ? 'Đang tra cứu…' : 'Tra cứu'}</Button>
        <Button type="button" variant="outline" onClick={() => applyForm(defaults)}>Đặt lại</Button>
        <Button type="button" variant="outline" onClick={() => { setPresetName(''); setNameDialog({ mode: 'save' }); }}>Lưu bộ lọc</Button>
      </div>
      <div className="preset-row"><NativeSelect aria-label="Bộ lọc đã lưu" defaultValue="" onChange={event => { const preset = presets.find(item => item.id === event.target.value); if (preset) { const params = { ...defaults, ...preset.params }; applyForm(params); void start(undefined, params); } }}><NativeSelectOption value="">Chạy lại bộ lọc đã lưu…</NativeSelectOption>{presets.map(item => <NativeSelectOption key={item.id} value={item.id}>{item.name}</NativeSelectOption>)}</NativeSelect></div>
    </form>
    {!!activeFilters.length && <div className="mb-4 flex flex-wrap items-center gap-2" aria-label="Bộ lọc đang áp dụng"><span className="text-sm text-muted-foreground">Đang lọc:</span>{activeFilters.map(item => <Button key={item.label} type="button" variant="secondary" size="sm" onClick={item.clear} aria-label={`Bỏ lọc ${item.label}`}>{item.label}<X size={14} aria-hidden="true"/></Button>)}<Button type="button" variant="ghost" size="sm" onClick={() => applyForm(defaults)}>Xóa tất cả</Button></div>}
    {!!presets.length && <details className="card"><summary>Bộ lọc đã lưu ({presets.length})</summary><div className="item-list">{presets.map(item => <article className="list-item" key={item.id}><strong>{item.pinned ? 'Ghim · ' : ''}{item.name}</strong><div className="form-actions"><Button variant="outline" onClick={() => { const params = { ...defaults, ...item.params }; applyForm(params); void start(undefined, params); }}>Chạy</Button><Button variant="outline" onClick={() => applyForm({ ...defaults, ...item.params })}>Nạp để sửa</Button><Button variant="outline" onClick={() => { setPresetName(item.name); setNameDialog({ mode: 'rename', item }); }}>Đổi tên</Button><Button variant="outline" onClick={() => void presetAction(item, 'pin')}>{item.pinned ? 'Bỏ ghim' : 'Ghim'}</Button><Button variant="outline" onClick={() => void presetAction(item, 'watch')}>{item.is_watch_enabled ? 'Tắt theo dõi' : 'Theo dõi'}</Button><Button variant="destructive" onClick={() => setDeletePreset(item)}>Xóa</Button></div></article>)}</div></details>}
    <Dialog open={!!nameDialog} onOpenChange={open => { if (!open) setNameDialog(null); }}><DialogContent><DialogHeader><DialogTitle>{nameDialog?.mode === 'save' ? 'Lưu bộ lọc' : 'Đổi tên bộ lọc'}</DialogTitle><DialogDescription>Đặt tên để tìm và chạy lại bộ lọc này.</DialogDescription></DialogHeader><form onSubmit={event => { event.preventDefault(); const name = presetName.trim(); if (!name) return; if (nameDialog?.mode === 'save') void savePreset(name); else if (nameDialog?.item) void presetAction(nameDialog.item, 'rename', name); }}><Input autoFocus aria-label="Tên bộ lọc" maxLength={80} value={presetName} onChange={event => setPresetName(event.target.value)}/><DialogFooter className="mt-4"><Button type="button" variant="outline" onClick={() => setNameDialog(null)}>Hủy</Button><Button disabled={!presetName.trim()}>Lưu</Button></DialogFooter></form></DialogContent></Dialog>
    <AlertDialog open={!!deletePreset} onOpenChange={open => { if (!open) setDeletePreset(null); }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Xóa bộ lọc?</AlertDialogTitle><AlertDialogDescription>{deletePreset?.name} sẽ bị xóa khỏi danh sách đã lưu.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Giữ lại</AlertDialogCancel><AlertDialogAction onClick={() => { if (deletePreset) void presetAction(deletePreset, 'delete'); }}>Xóa</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
    <section className="card results"><div className="results-head"><div><h2>Kết quả tra cứu</h2><p role="status">{phase === 'loading' ? message : phase === 'done' ? `${filtered.length.toLocaleString('vi-VN')} kết quả · đã chọn ${selected.size}${message.startsWith('Đã sao chép') ? ` · ${message}` : ''}` : phase === 'error' ? 'Không lấy được dữ liệu' : 'Chưa chạy truy vấn'}</p></div><div className="form-actions"><Link className="button secondary" to="/app/codes" state={jobId ? { jobId, indices: (selected.size ? rows.filter(row => selected.has(row.index)) : filtered).map(row => row.index) } : undefined}>Danh sách mã</Link>{compareCodes.length >= 2 && compareCodes.length <= 5 && <Link className="button secondary" to="/app/compare" state={{ codes: compareCodes }}>So sánh</Link>}<Button className="secondary" disabled={!jobId || !selected.size || busy} onClick={() => void exportRows()}>Xuất đã chọn</Button><Button disabled={!jobId || !rows.length || busy} onClick={() => void exportRows(true)}>Xuất tất cả</Button></div></div>
      {error && <p role="alert" className="error">{error} {phase === 'error' && <Button className="secondary" onClick={() => void start()}>Thử lại</Button>}</p>}
      {phase === 'loading' && <div className="skeleton" aria-label="Đang tải kết quả"/>}
      {phase === 'done' && !filtered.length && <EmptyState title="Không có gói phù hợp" description="Hãy đổi từ khóa hoặc điều kiện lọc rồi tra cứu lại."/>}
      {!!filtered.length && <>
        <div className="flex flex-wrap items-center justify-between gap-2 py-2"><p className="text-sm text-muted-foreground">Bấm tên cột để sao chép tất cả kết quả đang lọc. Shift + bấm để sắp xếp.</p><DropdownMenu><DropdownMenuTrigger asChild><Button variant="outline" size="sm"><Columns3 size={16}/> Cột hiển thị</Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuLabel>Hiển thị cột</DropdownMenuLabel>{columns.map(([key, label]) => <DropdownMenuCheckboxItem key={key} checked={visibleKeys.has(key)} onCheckedChange={() => toggleColumn(key)}>{label}</DropdownMenuCheckboxItem>)}</DropdownMenuContent></DropdownMenu></div>
        <div className="table-scroll"><Table><TableHeader><TableRow><TableHead className="w-10"><Checkbox aria-label="Chọn trang" checked={shown.length > 0 && shown.every(row => selected.has(row.index))} onCheckedChange={checked => { const next = new Set(selected); shown.forEach(row => { if (checked === true) next.add(row.index); else next.delete(row.index); }); setSelected(next); }}/></TableHead>
          {columns.filter(([key]) => visibleKeys.has(key)).map(([key, label]) => <TableHead key={key} aria-sort={sort === key ? descending ? 'descending' : 'ascending' : 'none'}><div className={`flex items-center gap-1 ${key === 'package_price' ? 'justify-end' : ''}`}><Button variant="ghost" size="sm" className="flex-1 justify-start" aria-label={`Sao chép toàn bộ cột ${label}`} onClick={event => { if (event.shiftKey) { setDescending(sort === key ? !descending : false); setSort(key); } else { void copyColumn(key); } }} title="Bấm để sao chép cả cột · Shift + bấm để sắp xếp">{label}</Button><Button variant="ghost" size="icon-xs" aria-label={`Sao chép cột ${label}`} title={`Sao chép toàn bộ cột ${label}`} onClick={() => void copyColumn(key)}><Copy size={14}/></Button></div></TableHead>)}<TableHead className="w-14">Thao tác</TableHead></TableRow></TableHeader>
          <TableBody>{shown.map(row => <TableRow key={row.index} data-state={selected.has(row.index) ? 'selected' : undefined}><TableCell><Checkbox aria-label={`Chọn ${tenderCode(row)}`} checked={selected.has(row.index)} onCheckedChange={checked => { const next = new Set(selected); if (checked === true) next.add(row.index); else next.delete(row.index); setSelected(next); }}/></TableCell>
            {columns.filter(([key]) => visibleKeys.has(key)).map(([key]) => <TableCell key={key} className={key === 'package_name' ? 'min-w-72 whitespace-normal' : key === 'package_price' ? 'text-right tabular-nums' : key === 'public_date' || key === 'bid_close_date' ? 'tabular-nums' : undefined}>{key === 'notify_no' ? <Link to={`/app/tenders/${encodeURIComponent(tenderCode(row))}`} state={{ row }}>{tenderCode(row)}</Link> : key === 'package_name' ? row.package_name || row.plan_name || '—' : key === 'tender_status' ? <Badge variant="secondary">{row.tender_status || 'Chưa rõ'}</Badge> : String(row[key] || '—')}</TableCell>)}
            <TableCell><DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label={`Thao tác ${tenderCode(row)}`}><MoreHorizontal size={16}/></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuItem onSelect={() => void toggleWatch(row)}><Star size={16}/>{watchlist.some(item => item.code === tenderCode(row)) ? 'Bỏ theo dõi' : 'Theo dõi'}</DropdownMenuItem><DropdownMenuItem onSelect={() => void navigator.clipboard.writeText(tenderCode(row)).catch(() => setError('Không sao chép được mã.'))}><Copy size={16}/> Sao chép mã</DropdownMenuItem>{row.source_url?.startsWith('https://muasamcong.mpi.gov.vn/') && <DropdownMenuItem onSelect={() => window.open(row.source_url, '_blank', 'noopener,noreferrer')}>Mở nguồn</DropdownMenuItem>}</DropdownMenuContent></DropdownMenu></TableCell></TableRow>)}</TableBody></Table></div>
        <Pagination page={page} total={filtered.length} pageSize={50} onChange={changePage}/>
      </>}
    </section></main>;
}
