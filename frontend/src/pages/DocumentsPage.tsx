import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { post, request } from '../api/client';
import { dateTime } from '../lib/format';

type Source = 'upload' | 'egp';
interface DocumentItem {
  id: string; source: Source; name: string; type: string; tender_code: string;
  khlcnt_code: string; tender_title: string; size: number | null; status: string;
  version: number; updated_at: string; is_new: boolean; ai_analyzed: boolean;
  snippet?: string; citation?: string;
}
interface Catalog { items: DocumentItem[]; total: number; has_more: boolean }
interface Detail {
  source: Source;
  document: Record<string, string | number | boolean | null>;
  chunks: Array<{ label: string; text: string }>;
  versions: Array<{ version: number; created_at: string; content_hash: string | null }>;
}

function queryString(params: URLSearchParams) {
  const result = new URLSearchParams(params);
  result.set('page_size', '25');
  return result;
}

export function DocumentsPage() {
  const [url, setUrl] = useSearchParams();
  const navigate = useNavigate();
  const { source, id } = useParams();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [query, setQuery] = useState(url.get('q') || '');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [tab, setTab] = useState<'overview' | 'preview' | 'versions'>('overview');
  const [compare, setCompare] = useState('');
  const [otherDocument, setOtherDocument] = useState('');
  const [tenderCode, setTenderCode] = useState('');
  const page = Math.max(1, Number(url.get('page')) || 1);
  const search = url.toString();

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    void request<Catalog>(`/api/document-center?${queryString(new URLSearchParams(search))}`, { signal: controller.signal })
      .then(setCatalog).catch(caught => { if (!controller.signal.aborted) setError(String(caught)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [search, revision]);

  useEffect(() => {
    if ((source !== 'upload' && source !== 'egp') || !id) { setDetail(null); return; }
    const controller = new AbortController();
    setDetail(null); setError(''); setTab('overview'); setCompare('');
    void request<Detail>(`/api/document-center/${source}/${id}`, { signal: controller.signal })
      .then(setDetail).catch(caught => { if (!controller.signal.aborted) setError(String(caught)); });
    return () => controller.abort();
  }, [source, id, revision]);

  function filter(key: string, value: string) {
    const next = new URLSearchParams(url);
    if (value) next.set(key, value); else next.delete(key);
    next.delete('page');
    setUrl(next, { replace: true });
  }
  function submit(event: FormEvent) { event.preventDefault(); filter('q', query.trim()); }
  function changePage(nextPage: number) { const next = new URLSearchParams(url); next.set('page', String(nextPage)); setUrl(next); }
  async function action(path: string, body: object = {}) {
    setBusy(true); setError(''); setNotice('');
    try { await post<unknown>(path, body); setNotice('Đã cập nhật tài liệu.'); setRevision(current => current + 1); }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }
  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; event.target.value = '';
    if (!file) return;
    setBusy(true); setError(''); setNotice('Đang tải tài liệu…');
    try {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(new Error('Không đọc được file.'));
        reader.readAsDataURL(file);
      });
      const result = await post<{ document: { id: string } }>('/api/documents/upload', {
        filename: file.name, mime_type: file.type || 'application/octet-stream',
        tender_code: tenderCode.trim(), data: dataUrl.split(',', 2)[1],
      });
      setNotice('Đã tải lên tài liệu.');
      setRevision(current => current + 1);
      navigate(`/app/documents/upload/${result.document.id}?${url}`);
    } catch (caught) { setNotice(''); setError(String(caught)); }
    finally { setBusy(false); }
  }
  async function compareVersions(first: number, second: number) {
    if (!id) return;
    setCompare('Đang so sánh…');
    try {
      const params = new URLSearchParams({ first: String(first), second: String(second) });
      const result = await request<{ metadata_changes: Array<{ field: string; before: string; after: string }>; text_diff: string[] }>(`/api/document-center/egp/${id}/compare?${params}`);
      setCompare([...result.metadata_changes.map(change => `${change.field}: ${change.before ?? '—'} → ${change.after ?? '—'}`), ...result.text_diff].join('\n') || 'Không có khác biệt.');
    } catch (caught) { setCompare(String(caught)); }
  }
  async function compareUploads() {
    if (!id || !otherDocument) return;
    setCompare('Đang so sánh…');
    try {
      const params = new URLSearchParams({ first: id, second: otherDocument });
      const result = await request<{ lines: string[] }>(`/api/document-center/compare?${params}`);
      setCompare(result.lines.join('\n') || 'Không có khác biệt trong nội dung đã đọc.');
    } catch (caught) { setCompare(String(caught)); }
  }
  const base = detail && id ? (detail.source === 'egp' ? `/api/document-center/egp/${id}` : `/api/documents/${id}`) : '';
  const doc = detail?.document;
  const name = String(doc?.document_name || doc?.filename || 'Tài liệu');
  const hasFile = detail?.source === 'upload' || doc?.has_file === true;
  const comparable = catalog?.items.filter(item => item.source === 'upload' && item.id !== id && item.tender_code && item.tender_code === doc?.tender_code && item.status === 'ready') || [];
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">TÀI LIỆU</p><h1>Trung tâm tài liệu</h1><p>Tài liệu đã tải lên và tài liệu gắn với gói thầu e-GP.</p></div><a className="button secondary" href={`/api/document-center/export?${queryString(url)}`}>Xuất danh mục</a></div>
    <form className="card form-grid" onSubmit={submit}><label className="wide">Tìm tài liệu<Input value={query} onChange={event => setQuery(event.target.value)} placeholder="Tên file, mã gói, nội dung…"/></label><label>Nguồn<NativeSelect value={url.get('source') || 'all'} onChange={event => filter('source', event.target.value)}><NativeSelectOption value="all">Tất cả</NativeSelectOption><NativeSelectOption value="upload">Tải lên</NativeSelectOption><NativeSelectOption value="egp">e-GP</NativeSelectOption></NativeSelect></label><label>Mã TBMT<Input value={url.get('tender_code') || ''} onChange={event => filter('tender_code', event.target.value)}/></label><label>Trạng thái<Input value={url.get('status') || ''} onChange={event => filter('status', event.target.value)}/></label><label>Sắp xếp<NativeSelect value={url.get('sort') || 'updated'} onChange={event => filter('sort', event.target.value)}><NativeSelectOption value="updated">Mới cập nhật</NativeSelectOption><NativeSelectOption value="name">Tên</NativeSelectOption><NativeSelectOption value="size">Dung lượng</NativeSelectOption></NativeSelect></label><div className="form-actions"><Button>Tìm kiếm</Button><Button type="button" className="secondary" onClick={() => { setQuery(''); setUrl({}); }}>Đặt lại</Button></div></form>
    <section className="card"><h2>Tải tài liệu riêng</h2><div className="form-actions"><Input aria-label="Mã TBMT liên quan" value={tenderCode} onChange={event => setTenderCode(event.target.value)} placeholder="Mã TBMT (nếu có)"/><Input aria-label="Chọn tài liệu" type="file" disabled={busy} onChange={event => void upload(event)}/></div></section>
    {error && <p role="alert" className="error">{error} <Button className="secondary" onClick={() => setRevision(current => current + 1)}>Thử lại</Button></p>}{notice && <p role="status">{notice}</p>}
    <div className="documents-layout"><section className="card"><div className="results-head"><h2>Danh mục</h2><small>{catalog?.total ?? 0} tài liệu</small></div>{loading ? <div className="skeleton"/> : !catalog?.items.length ? <p className="empty">Không có tài liệu trong phạm vi này.</p> : <div className="item-list">{catalog.items.map(item => <Link className={`list-item ${id === item.id ? 'selected-item' : ''}`} key={item.id} to={`/app/documents/${item.source}/${item.id}?${url}`}><span><strong>{item.name}</strong><small>{item.source === 'egp' ? 'e-GP' : 'Riêng'} · {item.tender_code || 'Không gắn gói'} · {item.status} · v{item.version} · {dateTime(item.updated_at)}</small>{item.snippet && <small>{item.snippet}</small>}</span>{item.is_new && <b>Mới</b>}</Link>)}</div>}<div className="pager"><Button className="secondary" disabled={page <= 1} onClick={() => changePage(page - 1)}>Trước</Button><span>Trang {page}</span><Button className="secondary" disabled={!catalog?.has_more} onClick={() => changePage(page + 1)}>Sau</Button></div></section>
      <section className="card"><div className="results-head"><h2>Chi tiết</h2>{id && <Link to={`/app/documents?${url}`}>Đóng</Link>}</div>{id && !detail && !error ? <div className="skeleton"/> : !detail ? <p className="empty">Chọn một tài liệu để xem chi tiết.</p> : <><h3>{name}</h3><p>{String(doc?.tender_code || 'Tài liệu riêng')} · {String(doc?.status || '')}</p><div className="form-actions">{hasFile && <a className="button secondary" href={`${base}/download`}>Tải file</a>}{detail.source === 'egp' ? <><Button disabled={busy} onClick={() => void action(`${base}/fetch`, { force: hasFile })}>{hasFile ? 'Kiểm tra bản mới' : 'Tải file nguồn'}</Button>{hasFile && <Button className="secondary" disabled={busy} onClick={() => void action(`${base}/extract`)}>Đọc nội dung</Button>}</> : <Button className="secondary" disabled={busy} onClick={() => void action(`${base}/process`)}>Xử lý văn bản</Button>}{doc?.tender_code && <Link to={`/app/tenders/${encodeURIComponent(String(doc.tender_code))}`}>Mở gói thầu</Link>}</div><div className="form-actions"><Button className={tab === 'overview' ? '' : 'secondary'} onClick={() => setTab('overview')}>Tổng quan</Button><Button className={tab === 'preview' ? '' : 'secondary'} onClick={() => setTab('preview')}>Nội dung</Button><Button className={tab === 'versions' ? '' : 'secondary'} onClick={() => setTab('versions')}>Phiên bản</Button></div>{tab === 'overview' && <dl className="facts"><div><span>Loại</span><strong>{String(doc?.document_type || doc?.mime_type || '—')}</strong></div><div><span>Cập nhật</span><strong>{dateTime(String(doc?.last_seen_at || doc?.updated_at || ''))}</strong></div><div><span>Dung lượng</span><strong>{doc?.file_size || doc?.size ? `${Math.round(Number(doc.file_size || doc.size) / 1024)} KB` : '—'}</strong></div></dl>}{tab === 'preview' && <>{detail.source === 'egp' && hasFile && doc?.mime_type === 'application/pdf' && <p><a href={`${base}/preview`} target="_blank" rel="noopener noreferrer">Xem trước PDF trong tab mới</a></p>}{detail.chunks.length ? <div className="document-chunks">{detail.chunks.map((chunk, index) => <article key={index}><small>{chunk.label}</small><p>{chunk.text}</p></article>)}</div> : <p className="empty">Chưa có nội dung trích xuất.</p>}</>}{tab === 'versions' && <>{detail.versions.length ? <><ul>{detail.versions.map(version => <li key={version.version}>v{version.version} · {dateTime(version.created_at)} · {version.content_hash || 'Chưa có hash'}</li>)}</ul>{detail.source === 'egp' && detail.versions.length >= 2 && <Button className="secondary" onClick={() => void compareVersions(detail.versions[1].version, detail.versions[0].version)}>So sánh 2 bản mới nhất</Button>}</> : <p className="empty">Chưa có lịch sử phiên bản.</p>}{detail.source === 'upload' && comparable.length > 0 && <div className="form-actions"><NativeSelect aria-label="Tài liệu để so sánh" value={otherDocument} onChange={event => setOtherDocument(event.target.value)}><NativeSelectOption value="">Chọn tài liệu cùng gói</NativeSelectOption>{comparable.map(item => <NativeSelectOption value={item.id} key={item.id}>{item.name}</NativeSelectOption>)}</NativeSelect><Button className="secondary" disabled={!otherDocument} onClick={() => void compareUploads()}>So sánh nội dung</Button></div>}{compare && <pre className="document-diff">{compare}</pre>}</>}</>}</section></div>
  </main>;
}
