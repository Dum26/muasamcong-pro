import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router';
import { download, post, request } from '../api/client';

interface CodeRow { code: string; code_type?: string; title?: string; investor_name?: string; tender_status?: string; lookup_error?: string; location?: string; bid_form?: string }
interface Extraction { id: string; state: string; rows: CodeRow[]; processed?: number; error?: string }
interface LotResult { files: Array<{ name: string; url?: string; archive_url?: string }>; issues: Array<{ reason?: string; code?: string }> }
const headers: Array<[keyof CodeRow, string]> = [['code', 'Mã'], ['code_type', 'Loại'], ['title', 'Tên gói / kế hoạch'], ['investor_name', 'Chủ đầu tư'], ['tender_status', 'Trạng thái'], ['location', 'Địa điểm'], ['bid_form', 'Hình thức']];

export function CodesPage() {
  const location = useLocation();
  const [text, setText] = useState(''); const [file, setFile] = useState<File | null>(null);
  const [deduplicate, setDeduplicate] = useState(true);
  const [data, setData] = useState<Extraction | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [lots, setLots] = useState<LotResult | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const active = useRef(0);
  useEffect(() => { const state = location.state as { jobId?: string; indices?: number[]; text?: string } | null;
    if (state?.text) setText(state.text);
    if (!state?.jobId) return;
    void start({ job_id: state.jobId, indices: state.indices || [], remove_duplicates: deduplicate });
    // Navigation state is consumed only on entry.
  }, [location.key]);
  useEffect(() => () => { active.current++; }, []);
  function clear() { active.current++; setData(null); setSelected(new Set()); setLots(null); setError(''); setNotice(''); }
  async function start(payload: object) {
    const ticket = ++active.current; setBusy(true); setError(''); setNotice(''); setLots(null); setData(null); setSelected(new Set());
    try {
      let next = await post<Extraction>('/api/extract', payload);
      if (ticket !== active.current) return;
      setData(next);
      while (next.state === 'running' || next.state === 'queued') {
        await new Promise(resolve => setTimeout(resolve, 650));
        if (ticket !== active.current) return;
        next = await request<Extraction>('/api/extraction?id=' + encodeURIComponent(next.id));
        if (ticket !== active.current) return;
        setData(next);
      }
      if (next.state === 'error') throw new Error(next.error || 'Không tra cứu được mã.');
      setSelected(new Set(next.rows.map((_, index) => index)));
      setNotice(`Đã lấy ${next.rows.length} mã.`);
    } catch (caught) { if (ticket === active.current) setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { if (ticket === active.current) setBusy(false); }
  }
  async function extract() {
    if (!text.trim() && !file) { setError('Hãy dán danh sách mã hoặc chọn file.'); return; }
    if (file && !/\.(xlsx|csv|txt)$/i.test(file.name)) { setError('Chỉ hỗ trợ .xlsx, .csv, .txt.'); return; }
    try {
      let fileBase64 = '';
      if (file) fileBase64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(String(reader.result || '').split(',')[1] || '');
        reader.onerror = () => reject(reader.error); reader.readAsDataURL(file);
      });
      await start({ text, filename: file?.name || '', file_base64: fileBase64, remove_duplicates: deduplicate });
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Không đọc được file.'); }
  }
  async function copyColumn(key: keyof CodeRow) {
    if (!data?.rows.length) return;
    try { await navigator.clipboard.writeText(data.rows.map(row => String(row[key] || (key === 'code_type' ? row.code.startsWith('PL') ? 'KHLCNT' : 'TBMT' : '—')).replace(/[\t\r\n]+/g, ' ')).join('\n')); setNotice(`Đã sao chép cột ${headers.find(item => item[0] === key)?.[1]}.`); }
    catch { setError('Không sao chép được. Hãy cấp quyền clipboard cho trình duyệt.'); }
  }
  async function exportCodes() { if (!data || data.state !== 'done') return; setBusy(true); setError('');
    try { await download('/api/export-codes', { extraction_id: data.id, expected_count: data.rows.length }, 'Danh_sach_ma.xlsx'); }
    catch (caught) { setError(String(caught)); } finally { setBusy(false); }
  }
  async function exportLots() { if (!data) return; const indices = [...selected].filter(index => data.rows[index]?.code.startsWith('IB'));
    if (!indices.length) { setError('Chọn mã TBMT (IB) có phân lô. KHLCNT (PL) không có file phân lô.'); return; }
    setBusy(true); setError(''); setLots(null);
    try { setLots(await post<LotResult>('/api/lots', { extraction_id: data.id, indices })); }
    catch (caught) { setError(String(caught)); } finally { setBusy(false); }
  }
  const rows = data?.rows || [];
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">DANH SÁCH MÃ</p><h1>Tra cứu mã TBMT và KHLCNT</h1><p>Dán mã hoặc nhập file, tra cứu thông tin và xuất Excel.</p></div></div>
    <section className="card"><label>Danh sách mã hoặc nội dung từ sheet<Textarea value={text} onChange={event => { setText(event.target.value); clear(); }} placeholder="IB2600…&#10;PL2600…" rows={6}/></label><div className="form-actions"><label>File .xlsx, .csv hoặc .txt<Input type="file" accept=".xlsx,.csv,.txt" onChange={event => { setFile(event.target.files?.[0] || null); clear(); }}/></label><label className="check"><Checkbox checked={deduplicate} onCheckedChange={checked => { setDeduplicate(checked === true); clear(); }}/> Bỏ mã trùng</label><Button disabled={busy} onClick={() => void extract()}>{busy ? 'Đang tra cứu…' : 'Phân tích dữ liệu'}</Button></div></section>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}{busy && <div className="card skeleton" aria-label="Đang tra cứu thông tin mã"/>}
    <section className="card"><div className="results-head"><div><h2>{rows.length} mã · đã chọn {selected.size}</h2><p>{data?.state === 'running' ? `Đang lấy thông tin: ${data.processed || 0}/${rows.length}` : data ? 'Chọn tiêu đề cột để sao chép cả cột.' : 'Chưa có danh sách mã.'}</p></div><div className="form-actions"><Button className="secondary" disabled={!rows.length} onClick={() => void copyColumn('code')}>Sao chép mã</Button><Button className="secondary" disabled={busy || data?.state !== 'done' || !rows.length} onClick={() => void exportCodes()}>Xuất Excel</Button><Button disabled={busy || ![...selected].some(index => rows[index]?.code.startsWith('IB'))} onClick={() => void exportLots()}>Tải Excel phân lô ({[...selected].filter(index => rows[index]?.code.startsWith('IB')).length} IB)</Button></div></div>
      {rows.length ? <div className="table-scroll"><Table><TableHeader><TableRow><TableHead><Checkbox aria-label="Chọn tất cả" checked={selected.size === rows.length} onCheckedChange={checked => setSelected(checked === true ? new Set(rows.map((_, index) => index)) : new Set())}/></TableHead><TableHead>STT</TableHead>{headers.map(([key, label]) => <TableHead key={key}><Button className="column-sort" onClick={() => void copyColumn(key)} title={`Sao chép cột ${label}`}>{label}</Button></TableHead>)}</TableRow></TableHeader><TableBody>{rows.map((row, index) => <TableRow key={`${row.code}-${index}`}><TableCell><Checkbox aria-label={`Chọn ${row.code}`} checked={selected.has(index)} onCheckedChange={checked => { const next = new Set(selected); if (checked === true) next.add(index); else next.delete(index); setSelected(next); }}/></TableCell><TableCell>{index + 1}</TableCell><TableCell>{row.code.startsWith('PL') ? <Link to={`/app/plans/${encodeURIComponent(row.code)}`}>{row.code}</Link> : <Link to={`/app/tenders/${encodeURIComponent(row.code)}`}>{row.code}</Link>}</TableCell><TableCell>{row.code_type || (row.code.startsWith('PL') ? 'KHLCNT' : 'TBMT')}</TableCell><TableCell>{row.title || '—'}</TableCell><TableCell>{row.investor_name || '—'}</TableCell><TableCell>{row.tender_status || row.lookup_error || '—'}</TableCell><TableCell>{row.location || '—'}</TableCell><TableCell>{row.bid_form || '—'}</TableCell></TableRow>)}</TableBody></Table></div> : <p className="empty">Dán mã hoặc chọn file để bắt đầu.</p>}</section>
    {lots && <section className="card"><h2>File phân lô</h2>{lots.files?.length ? <div className="item-list">{lots.files.map((item, index) => <a className="list-item" key={index} href={item.archive_url || item.url} download>{item.name}</a>)}</div> : <p>Không có file phân lô cho các mã đã chọn.</p>}{lots.issues?.map((issue, index) => <p key={index}>{issue.code || 'Mã đã chọn'}: {issue.reason || 'Không có file'}</p>)}</section>}
  </main>;
}
