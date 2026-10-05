import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router';
import { request } from '../api/client';
import { workspaceApi } from '../api/core';
import type { SavedSearch } from '../types';
import { toast } from 'sonner';
import { Star } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/shared/EmptyState';
import { Pagination } from '@/components/data-table/Pagination';

interface Item { kind: string; code: string; name: string; published: string | null; deadline: string | null; price: string | null; status: string | null; investor: string | null; updated: string | null }
interface Results { items: Item[]; total: number; page: number; total_pages: number }
const kinds: Record<string, string> = { '': 'Tất cả', tender: 'TBMT', plan: 'KHLCNT', investor: 'Chủ đầu tư', procurer: 'Bên mời thầu', contractor: 'Nhà thầu' };
const fields: Array<[string, string, string]> = [['q', 'Từ khóa, mã hoặc tên', 'text'], ['status', 'Trạng thái', 'text'], ['location', 'Địa điểm', 'text'], ['investor', 'Chủ đầu tư', 'text'], ['procurer', 'Bên mời thầu', 'text'], ['contractor', 'Nhà thầu', 'text'], ['from', 'Đăng từ ngày', 'date'], ['to', 'Đăng đến ngày', 'date'], ['deadline_from', 'Đóng thầu từ', 'date'], ['deadline_to', 'Đóng thầu đến', 'date'], ['price_min', 'Giá từ', 'number'], ['price_max', 'Giá đến', 'number'], ['selection_method', 'Hình thức LCNT', 'text'], ['contract_type', 'Loại hợp đồng', 'text']];

export function ArchiveSearchPage() {
  const [url, setUrl] = useSearchParams(); const search = url.toString();
  const [draft, setDraft] = useState(() => Object.fromEntries(new URLSearchParams(search)));
  const [data, setData] = useState<Results | null>(null); const [presets, setPresets] = useState<SavedSearch[]>([]);
  const [loading, setLoading] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [saveOpen, setSaveOpen] = useState(false); const [saveName, setSaveName] = useState('');
  useEffect(() => { void workspaceApi.presets().then(result => setPresets(result.presets)).catch(() => {}); }, []);
  useEffect(() => { setDraft(Object.fromEntries(new URLSearchParams(search))); if (!url.has('run')) return;
    const controller = new AbortController(); setLoading(true); setError('');
    const params = new URLSearchParams(search); params.delete('run');
    void request<Results>(`/api/intelligence/search?${params}`, { signal: controller.signal }).then(setData)
      .catch(caught => { if (!controller.signal.aborted) setError(String(caught)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [search]);
  function update(key: string, value: string) { setDraft(current => ({ ...current, [key]: value })); }
  function submit(event?: FormEvent) { event?.preventDefault(); const params = new URLSearchParams();
    for (const [key, value] of Object.entries(draft)) if (value && key !== 'page') params.set(key, value);
    params.set('page', '1'); params.set('page_size', '25'); params.set('run', '1'); setUrl(params);
    void workspaceApi.historyAction({ params: { mode: 'Kho dữ liệu', keyword: draft.q || '', ...draft } }).catch(() => {});
  }
  function page(next: number) { const params = new URLSearchParams(url); params.set('page', String(next)); params.set('run', '1'); setUrl(params); }
  async function save() { const name = saveName.trim(); if (!name) return;
    try { setPresets((await workspaceApi.presetAction({ action: 'save', name, params: { ...draft, mode: 'Kho dữ liệu', keyword: draft.q || '' } })).presets); setNotice('Đã lưu bộ lọc.'); setSaveOpen(false); toast.success('Đã lưu bộ lọc.'); }
    catch (caught) { const message = String(caught); setError(message); toast.error(message); }
  }
  async function follow(item: Item) { try { await workspaceApi.watch({ action: 'add', code: item.code, name: item.name, investor: item.investor || '', deadline: item.deadline || '', row: { package_name: item.name, investor_name: item.investor || '', bid_close_date: item.deadline || '', tender_status: item.status || '' } }); setNotice(`Đã theo dõi ${item.code}.`); toast.success(`Đã theo dõi ${item.code}.`); }
    catch (caught) { setError(String(caught)); } }
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">KHO DỮ LIỆU</p><h1>Tìm trong dữ liệu đã thu thập</h1><p>Tìm TBMT, KHLCNT, chủ đầu tư, bên mời thầu và nhà thầu.</p></div><div className="form-actions"><Link to="/app/compare">So sánh gói</Link><Link to="/app/search">Tra cứu trực tiếp e-GP</Link></div></div>
    <form className="card" onSubmit={submit}><div className="form-grid"><label>Loại<NativeSelect value={draft.kind || ''} onChange={event => update('kind', event.target.value)}>{Object.entries(kinds).map(([key, label]) => <NativeSelectOption key={key} value={key}>{label}</NativeSelectOption>)}</NativeSelect></label>{fields.map(([key, label, type]) => <label className={key === 'q' ? 'wide' : ''} key={key}>{label}<Input type={type} value={draft[key] || ''} onChange={event => update(key, event.target.value)}/></label>)}<label>Sắp xếp<NativeSelect value={draft.sort || 'relevance'} onChange={event => update('sort', event.target.value)}><NativeSelectOption value="relevance">Liên quan</NativeSelectOption><NativeSelectOption value="published">Ngày đăng</NativeSelectOption><NativeSelectOption value="deadline">Đóng thầu</NativeSelectOption><NativeSelectOption value="price">Giá</NativeSelectOption><NativeSelectOption value="name">Tên</NativeSelectOption><NativeSelectOption value="updated">Cập nhật</NativeSelectOption></NativeSelect></label><label>Thứ tự<NativeSelect value={draft.order || 'desc'} onChange={event => update('order', event.target.value)}><NativeSelectOption value="desc">Giảm dần</NativeSelectOption><NativeSelectOption value="asc">Tăng dần</NativeSelectOption></NativeSelect></label><label className="check"><Checkbox checked={draft.results === '1'} onCheckedChange={checked => update('results', checked === true ? '1' : '')}/> Chỉ có KQLCNT</label></div><div className="form-actions"><Button disabled={loading}>{loading ? 'Đang tìm…' : 'Tìm kiếm'}</Button><Button type="button" variant="outline" onClick={() => { setSaveName(''); setSaveOpen(true); }}>Lưu bộ lọc</Button><Button type="button" variant="outline" onClick={() => { setDraft({}); setUrl({}); setData(null); }}>Đặt lại</Button><NativeSelect aria-label="Bộ lọc đã lưu" value="" onChange={event => { const item = presets.find(saved => saved.id === event.target.value); if (!item) return; const params = new URLSearchParams(Object.entries(item.params).filter((entry): entry is [string, string] => typeof entry[1] === 'string')); params.delete('mode'); params.delete('keyword'); params.set('q', item.params.keyword || params.get('q') || ''); params.set('run', '1'); setUrl(params); }}><NativeSelectOption value="">Chạy bộ lọc đã lưu…</NativeSelectOption>{presets.filter(item => (item.params as unknown as { mode?: string }).mode === 'Kho dữ liệu').map(item => <NativeSelectOption key={item.id} value={item.id}>{item.name}</NativeSelectOption>)}</NativeSelect></div></form>
    <Dialog open={saveOpen} onOpenChange={setSaveOpen}><DialogContent><DialogHeader><DialogTitle>Lưu bộ lọc</DialogTitle><DialogDescription>Đặt tên để chạy lại bộ lọc này.</DialogDescription></DialogHeader><form onSubmit={event => { event.preventDefault(); void save(); }}><Input autoFocus aria-label="Tên bộ lọc" maxLength={80} value={saveName} onChange={event => setSaveName(event.target.value)}/><DialogFooter className="mt-4"><Button type="button" variant="outline" onClick={() => setSaveOpen(false)}>Hủy</Button><Button disabled={!saveName.trim()}>Lưu</Button></DialogFooter></form></DialogContent></Dialog>
    {error && <p role="alert" className="error">{error} <Button className="secondary" onClick={() => submit()}>Thử lại</Button></p>}{notice && <p role="status">{notice}</p>}
    <section className="card"><h2>Kết quả {data ? `· ${data.total.toLocaleString('vi-VN')}` : ''}</h2>{loading ? <Skeleton className="h-48" aria-label="Đang tải kết quả"/> : !data ? <EmptyState title="Chưa tìm kiếm" description="Nhập điều kiện rồi tìm trong dữ liệu đã thu thập."/> : !data.items.length ? <EmptyState title="Không có dữ liệu phù hợp" description="Thử nới điều kiện lọc hoặc đổi từ khóa."/> : <><div className="table-scroll"><Table><TableHeader><TableRow>{['Loại', 'Mã', 'Tên', 'Chủ đầu tư', 'Ngày đăng', 'Đóng thầu', 'Trạng thái', 'Thao tác'].map(label => <TableHead key={label}>{label}</TableHead>)}</TableRow></TableHeader><TableBody>{data.items.map(item => <TableRow key={`${item.kind}-${item.code}`}><TableCell>{kinds[item.kind] || item.kind}</TableCell><TableCell>{item.kind === 'tender' || item.kind === 'plan' ? <Link to={item.kind === 'plan' ? `/app/plans/${encodeURIComponent(item.code)}` : `/app/tenders/${encodeURIComponent(item.code)}`}>{item.code}</Link> : <Link to={`/app/entities/${item.kind}/${encodeURIComponent(item.code)}`}>{item.code}</Link>}</TableCell><TableCell className="min-w-72 whitespace-normal">{item.name}</TableCell><TableCell>{item.investor || '—'}</TableCell><TableCell>{item.published || '—'}</TableCell><TableCell>{item.deadline || '—'}</TableCell><TableCell><Badge variant="secondary">{item.status || 'Chưa rõ'}</Badge></TableCell><TableCell>{['tender', 'plan'].includes(item.kind) && <Button variant="outline" size="sm" onClick={() => void follow(item)}><Star size={14}/> Theo dõi</Button>}</TableCell></TableRow>)}</TableBody></Table></div><Pagination page={data.page} total={data.total} pageSize={25} onChange={page}/></>}</section>
  </main>;
}
