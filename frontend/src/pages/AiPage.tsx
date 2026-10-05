import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { download, downloadGet, post, request } from '../api/client';
import { dateTime } from '../lib/format';

interface Config { configured: boolean; provider: string; model: string; max_upload_mb: number; inline_extract_mb: number }
interface Document { id: string; filename: string; tender_code: string; size: number; status: string; scan_likely: boolean; error: string; created_at: string }
interface Chunk { source_id: string; label: string; text: string }
interface Content { chunks: Chunk[]; has_more: boolean; document: Document }
interface Citation { source_id: string; label: string }
interface Result {
  answer?: string; citations?: Citation[];
  sections?: Array<{ title: string; items: Array<{ label: string; value: string; citations: Citation[] }> }>;
  table?: Array<{ item: string; unit: string; quantity: string; technical: string; origin: string; delivery: string; citations: Citation[] }>;
  comparison?: Array<{ criterion: string; value_a: string; value_b: string; change: string; citations_a: Citation[]; citations_b: Citation[] }>;
  compare_document_id?: string;
}
interface Analysis { id: string; analysis_type: string; model: string; created_at: string; result: Result; cached?: boolean }
const operations = [
  ['summary', 'Tóm tắt'], ['catalog', 'Danh mục hàng hóa'], ['capacity', 'Năng lực'],
  ['technical', 'Kỹ thuật'], ['evaluation', 'Tiêu chí đánh giá'], ['timeline', 'Tiến độ'],
  ['bid_security', 'Bảo đảm dự thầu'], ['contract', 'Hợp đồng'], ['qa', 'Hỏi đáp'],
  ['compare', 'So sánh hai hồ sơ'], ['compare_versions', 'So sánh hai phiên bản'],
] as const;

export function citationTarget(sourceId: string, selected: string, related: string) {
  const source = sourceId.replace(/^[AB]:/, '');
  const index = Number(source.slice(1));
  return { documentId: sourceId.startsWith('B:') ? related : selected,
    source, page: Number.isFinite(index) ? Math.max(1, Math.ceil(index / 80)) : 1 };
}

export function AiPage() {
  const [config, setConfig] = useState<Config | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [page, setPage] = useState(1); const [hasMore, setHasMore] = useState(false);
  const [selected, setSelected] = useState(''); const [viewer, setViewer] = useState('');
  const [chunks, setChunks] = useState<Chunk[]>([]); const [contentPage, setContentPage] = useState(1);
  const [contentMore, setContentMore] = useState(false);
  const [history, setHistory] = useState<Analysis[]>([]); const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [operation, setOperation] = useState('summary'); const [question, setQuestion] = useState('');
  const [related, setRelated] = useState(''); const [tenderCode, setTenderCode] = useState('');
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => { const controller = new AbortController();
    void Promise.all([request<Config>('/api/ai/config', { signal: controller.signal }),
      request<{ items: Document[]; has_more: boolean }>(`/api/documents?page=${page}`, { signal: controller.signal })])
      .then(([settings, list]) => { setConfig(settings); setDocuments(list.items); setHasMore(list.has_more); })
      .catch(caught => { if (!controller.signal.aborted) setError(String(caught)); });
    return () => controller.abort();
  }, [page, revision]);
  useEffect(() => { if (!selected) { setChunks([]); setHistory([]); return; }
    const controller = new AbortController(); setAnalysis(null); setViewer(selected); setContentPage(1); setError('');
    void Promise.all([request<Content>(`/api/documents/${selected}/content?page=1`, { signal: controller.signal }),
      request<{ items: Analysis[] }>(`/api/documents/${selected}/analyses`, { signal: controller.signal })])
      .then(([content, previous]) => { setChunks(content.chunks); setContentMore(content.has_more); setHistory(previous.items.filter(item => item.result)); setTenderCode(content.document.tender_code || ''); })
      .catch(caught => { if (!controller.signal.aborted) setError(String(caught)); });
    return () => controller.abort();
  }, [selected, revision]);
  async function moreContent(target = viewer, nextPage = contentPage + 1, append = true) {
    try { const content = await request<Content>(`/api/documents/${target}/content?page=${nextPage}`);
      setViewer(target); setContentPage(nextPage); setChunks(current => append && target === viewer ? [...current, ...content.chunks] : content.chunks); setContentMore(content.has_more);
    } catch (caught) { setError(String(caught)); }
  }
  async function act(path: string, body: object = {}) {
    setBusy(true); setError(''); setNotice('');
    try { await post(path, body); setRevision(current => current + 1); setNotice('Đã cập nhật tài liệu.'); }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }
  async function run(refresh = false) {
    if (!selected) return; if (operation === 'qa' && !question.trim()) { setError('Hãy nhập câu hỏi.'); return; }
    if (operation.startsWith('compare') && !related) { setError('Hãy chọn tài liệu thứ hai.'); return; }
    setBusy(true); setError(''); setNotice('Đang phân tích nội dung có dẫn nguồn…');
    try { const result = await post<Analysis>('/api/ai/analyze', {
      document_id: selected, operation, question: operation === 'qa' ? question.trim() : '',
      related_document_id: operation.startsWith('compare') ? related : '', refresh,
    }); setAnalysis(result); setHistory((await request<{ items: Analysis[] }>(`/api/documents/${selected}/analyses`)).items.filter(item => item.result));
      setNotice(result.cached ? 'Đã mở kết quả đã lưu.' : 'Phân tích hoàn tất.');
    } catch (caught) { setNotice(''); setError(String(caught)); }
    finally { setBusy(false); }
  }
  async function jump(sourceId: string) {
    const target = citationTarget(sourceId, selected, analysis?.result?.compare_document_id || related);
    if (target.documentId && (viewer !== target.documentId || contentPage !== target.page)) await moreContent(target.documentId, target.page, false);
    requestAnimationFrame(() => document.getElementById(`ai-source-${target.source}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  }
  async function copyAnalysis() {
    if (!analysis?.result) return;
    try { await navigator.clipboard.writeText(JSON.stringify(analysis.result, null, 2)); setNotice('Đã sao chép kết quả.'); }
    catch (caught) { setError(String(caught)); }
  }
  const current = documents.find(item => item.id === selected);
  const citations = (items: Citation[] = []) => items.map(citation => <Button className="secondary" key={citation.source_id} onClick={() => void jump(citation.source_id)}>{citation.label}</Button>);
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">AI HỒ SƠ</p><h1>Phân tích tài liệu đấu thầu</h1><p>{config?.configured ? `Sẵn sàng · ${config.provider} / ${config.model}` : 'AI chưa được cấu hình; vẫn có thể xem và quản lý tài liệu.'}</p></div><Link className="button" to="/app/documents">Tải tài liệu lên</Link></div>
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="documents-layout"><section className="card"><div className="results-head"><h2>Tài liệu riêng</h2><span>{documents.length}{hasMore ? '+' : ''} file</span></div>{documents.length ? <div className="item-list">{documents.map(doc => <Button className={`list-item document-choice ${selected === doc.id ? 'selected-item' : ''}`} key={doc.id} onClick={() => setSelected(doc.id)}><span><strong>{doc.filename}</strong><small>{doc.tender_code || 'Chưa liên kết gói'} · {doc.status} · {dateTime(doc.created_at)}</small></span></Button>)}</div> : <p className="empty">Chưa có tài liệu riêng.</p>}<div className="pager"><Button className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Trước</Button><span>Trang {page}</span><Button className="secondary" disabled={!hasMore} onClick={() => setPage(page + 1)}>Sau</Button></div></section>
      <section className="card"><h2>{current?.filename || 'Chọn tài liệu'}</h2>{current && <><p>{current.status} · {Math.round(current.size / 1024)} KB{current.scan_likely ? ' · Có thể là PDF scan' : ''}</p>{current.error && <p className="error">{current.error}</p>}<div className="form-actions"><Button className="secondary" onClick={() => void downloadGet(`/api/documents/${selected}/download`, current.filename).catch(caught => setError(String(caught)))}>Tải file</Button><Button className="secondary" disabled={busy} onClick={() => void act(`/api/documents/${selected}/process`)}>Đọc nội dung</Button></div><div className="form-actions"><Input aria-label="Mã TBMT hoặc KHLCNT" value={tenderCode} onChange={event => setTenderCode(event.target.value)} placeholder="Mã TBMT/KHLCNT"/><Button className="secondary" disabled={busy} onClick={() => void act(`/api/documents/${selected}/link`, { tender_code: tenderCode })}>Liên kết gói</Button></div><div className="document-chunks">{chunks.length ? chunks.map(chunk => <article id={`ai-source-${chunk.source_id}`} key={chunk.source_id}><small>{chunk.label}</small><p>{chunk.text}</p><Button className="secondary" onClick={() => void navigator.clipboard.writeText(chunk.text).catch(caught => setError(String(caught)))}>Sao chép đoạn</Button></article>) : <p className="empty">Chưa có văn bản trích xuất.</p>}</div>{contentMore && <Button className="secondary" onClick={() => void moreContent()}>Đọc tiếp</Button>}</>}</section></div>
    <section className="card"><h2>Phân tích có dẫn nguồn</h2><div className="form-grid"><label>Thao tác<NativeSelect value={operation} onChange={event => setOperation(event.target.value)}>{operations.map(([value, label]) => <NativeSelectOption key={value} value={value}>{label}</NativeSelectOption>)}</NativeSelect></label>{operation === 'qa' && <label className="wide">Câu hỏi<Input value={question} onChange={event => setQuestion(event.target.value)} placeholder="Tài liệu yêu cầu bảo đảm dự thầu bao nhiêu?"/></label>}{operation.startsWith('compare') && <label className="wide">Tài liệu thứ hai<NativeSelect value={related} onChange={event => setRelated(event.target.value)}><NativeSelectOption value="">Chọn tài liệu</NativeSelectOption>{documents.filter(doc => doc.id !== selected && doc.status === 'ready').map(doc => <NativeSelectOption key={doc.id} value={doc.id}>{doc.filename}</NativeSelectOption>)}</NativeSelect></label>}</div><div className="form-actions"><Button disabled={!config?.configured || current?.status !== 'ready' || busy} onClick={() => void run()}>{busy ? 'Đang xử lý…' : 'Phân tích'}</Button><Button className="secondary" disabled={!config?.configured || current?.status !== 'ready' || busy} onClick={() => void run(true)}>Phân tích lại</Button></div>{analysis && <div className="analysis-result"><p>{analysis.cached ? 'Kết quả đã lưu' : 'Kết quả mới'} · {analysis.model} · {dateTime(analysis.created_at)}</p>{analysis.result.answer && <article><h3>Kết quả</h3><p>{analysis.result.answer}</p><div className="form-actions">{citations(analysis.result.citations)}</div></article>}{analysis.result.sections?.map((section, index) => <article key={index}><h3>{section.title}</h3>{section.items.map((item, itemIndex) => <div key={itemIndex}><strong>{item.label}</strong><p>{item.value}</p><div className="form-actions">{citations(item.citations)}</div></div>)}</article>)}{!!analysis.result.table?.length && <div className="table-scroll"><Table><TableHeader><TableRow><TableHead>Hàng hóa/dịch vụ</TableHead><TableHead>Đơn vị</TableHead><TableHead>SL</TableHead><TableHead>Kỹ thuật</TableHead><TableHead>Xuất xứ</TableHead><TableHead>Nguồn</TableHead></TableRow></TableHeader><TableBody>{analysis.result.table.map((row, index) => <TableRow key={index}><TableCell>{row.item}</TableCell><TableCell>{row.unit}</TableCell><TableCell>{row.quantity}</TableCell><TableCell>{row.technical}</TableCell><TableCell>{row.origin}</TableCell><TableCell>{citations(row.citations)}</TableCell></TableRow>)}</TableBody></Table></div>}{!!analysis.result.comparison?.length && <div className="table-scroll"><Table><TableHeader><TableRow><TableHead>Tiêu chí</TableHead><TableHead>Hồ sơ A</TableHead><TableHead>Hồ sơ B</TableHead><TableHead>Thay đổi</TableHead></TableRow></TableHeader><TableBody>{analysis.result.comparison.map((row, index) => <TableRow key={index}><TableCell>{row.criterion}</TableCell><TableCell>{row.value_a}{citations(row.citations_a)}</TableCell><TableCell>{row.value_b}{citations(row.citations_b)}</TableCell><TableCell>{row.change}</TableCell></TableRow>)}</TableBody></Table></div>}<div className="form-actions"><Button className="secondary" onClick={() => void copyAnalysis()}>Sao chép</Button><Button className="secondary" onClick={() => void download('/api/ai/export', { analysis_id: analysis.id, format: 'xlsx' }, 'Phan_tich.xlsx').catch(caught => setError(String(caught)))}>Excel</Button><Button className="secondary" onClick={() => void download('/api/ai/export', { analysis_id: analysis.id, format: 'docx' }, 'Phan_tich.docx').catch(caught => setError(String(caught)))}>Word</Button></div></div>}</section>
    <section className="card"><h2>Lịch sử phân tích</h2>{history.length ? <div className="item-list">{history.map(item => <Button className="list-item document-choice" key={item.id} onClick={() => setAnalysis(item)}><span><strong>{operations.find(([key]) => key === item.analysis_type)?.[1] || item.analysis_type}</strong><small>{dateTime(item.created_at)} · {item.model}</small></span></Button>)}</div> : <p className="empty">Chưa có phân tích cho tài liệu này.</p>}</section>
  </main>;
}
