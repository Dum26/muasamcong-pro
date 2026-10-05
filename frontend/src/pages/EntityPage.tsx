import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';
import { request } from '../api/client';

interface Profile { kind: string; entity: Record<string, string | null>; items: Array<{ tender_code: string; title: string; publish_date: string; status: string; package_price: string | null }>; total: number; page: number; page_size: number; stats: { tenders: number; package_value: string | null; winning_value: string | null; results: number } }
const names: Record<string, string> = { investor: 'Chủ đầu tư', contractor: 'Nhà thầu', procurer: 'Bên mời thầu' };
export function EntityPage() {
  const { kind = '', id = '' } = useParams(); const [url, setUrl] = useSearchParams();
  const [data, setData] = useState<Profile | null>(null); const [error, setError] = useState(''); const [loading, setLoading] = useState(true);
  const search = url.toString();
  useEffect(() => { if (!names[kind]) return; const controller = new AbortController(); setLoading(true); setError('');
    void request<Profile>(`/api/intelligence/entities/${kind}/${encodeURIComponent(id)}?${search}`, { signal: controller.signal })
      .then(setData).catch(caught => { if (!controller.signal.aborted) setError(String(caught)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [kind, id, search]);
  function filter(key: string, value: string) { const next = new URLSearchParams(url); if (value) next.set(key, value); else next.delete(key); if (key !== 'page') next.delete('page'); setUrl(next); }
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">{names[kind] || 'ĐƠN VỊ'}</p><h1>{data?.entity.name || 'Hồ sơ đơn vị'}</h1><p>{data?.entity.tax_code || data?.entity.identifier || 'Chưa có mã định danh'}</p></div><Link to="/app/archive">← Kho dữ liệu</Link></div>{error && <p role="alert" className="error">{error}</p>}{loading ? <div className="card skeleton"/> : data && <><div className="kpi-grid">{([['tenders', 'Gói liên quan'], ['results', 'Có KQLCNT'], ['package_value', 'Tổng giá gói'], ['winning_value', 'Tổng giá trúng']] as const).map(([key, label]) => <article className="card" key={key}><small>{label}</small><strong>{data.stats[key] ?? '—'}</strong></article>)}</div><section className="card"><h2>Gói thầu liên quan</h2><div className="form-grid"><label>Tìm mã hoặc tên<Input value={url.get('q') || ''} onChange={event => filter('q', event.target.value)}/></label><label>Trạng thái<Input value={url.get('status') || ''} onChange={event => filter('status', event.target.value)}/></label><label>Từ ngày<Input type="date" value={url.get('from') || ''} onChange={event => filter('from', event.target.value)}/></label><label>Đến ngày<Input type="date" value={url.get('to') || ''} onChange={event => filter('to', event.target.value)}/></label></div>{data.items.length ? <div className="item-list">{data.items.map(item => <Link className="list-item" key={item.tender_code} to={`/app/tenders/${encodeURIComponent(item.tender_code)}`}><strong>{item.title || item.tender_code}</strong><small>{item.tender_code} · {item.publish_date || '—'} · {item.status || '—'}</small></Link>)}</div> : <p className="empty">Không có gói phù hợp.</p>}<div className="pager"><Button className="secondary" disabled={data.page <= 1} onClick={() => filter('page', String(data.page - 1))}>Trước</Button><span>Trang {data.page} · {data.total} gói</span><Button className="secondary" disabled={data.page * data.page_size >= data.total} onClick={() => filter('page', String(data.page + 1))}>Sau</Button></div></section></>}</main>;
}
