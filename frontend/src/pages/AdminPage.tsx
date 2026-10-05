import { AdminUsersPanel } from './AdminUsersPanel';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useEffect, useState } from 'react';
import { useConfirm } from '@/components/shared/ConfirmProvider';
import { post, request } from '../api/client';
import { QualityPanel } from './QualityPanel';

type Data = Record<string, unknown>;
type Job = { id: number; entity_id: string; job_type: string; status: string; attempts: number; last_error?: string };
const fmt = (value: unknown) => typeof value === 'number' ? value.toLocaleString('vi-VN') : String(value ?? '—');
const metrics: [string, string][] = [['total_users', 'Tài khoản'], ['active_users', 'Đang hoạt động'], ['searches_today', 'Truy vấn hôm nay'], ['followed_tenders', 'Gói theo dõi'], ['downloads', 'Lượt xuất file'], ['automation_active_rules', 'Rule đang bật']];

export function AdminPage() {
  const confirmAction = useConfirm();
  const [tab, setTab] = useState<'overview' | 'users' | 'sync' | 'quality' | 'performance'>('overview');
  const [stats, setStats] = useState<Data>({});
  const [production, setProduction] = useState<Data>({});
  const [sync, setSync] = useState<Data>({});
  const [performance, setPerformance] = useState<Data>({});
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    const load = async () => {
      setError('');
      try {
        if (tab === 'overview') {
          const [a, b] = await Promise.all([request<Data>('/api/admin/stats'), request<Data>('/api/admin/production-status')]);
          if (active) { setStats(a); setProduction(b); }
        } else if (tab === 'sync') {
          const data = await request<Data>('/api/data-sync');
          if (active) setSync(data);
        } else if (tab === 'quality' || tab === 'users') {
          return;
        } else {
          const data = await request<Data>('/api/admin/performance');
          if (active) setPerformance(data);
        }
      } catch (caught) { if (active) setError(caught instanceof Error ? caught.message : String(caught)); }
    };
    void load();
    return () => { active = false; };
  }, [tab, revision]);
  async function action(path: string, body: object, confirmText?: string) {
    if (confirmText && !await confirmAction(confirmText)) return;
    setBusy(true); setError(''); setNotice('');
    try { await post<unknown>(path, body); setNotice('Đã thực hiện.'); setRevision(value => value + 1); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { setBusy(false); }
  }
  const sources = (sync.sources || []) as Array<{ id: string; name: string; is_enabled: boolean }>;
  const jobs = (sync.jobs || []) as Job[];
  const routes = (performance.routes || []) as Array<{ route: string; count: number; p50_ms: number; p95_ms: number; errors_5xx: number }>;
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">QUẢN TRỊ</p><h1>Vận hành hệ thống</h1><p>Trạng thái, đồng bộ và chất lượng dữ liệu của máy chủ hiện tại.</p></div><Button className="secondary" disabled={busy} onClick={() => setRevision(value => value + 1)}>Làm mới</Button></div>
    <div className="form-actions" role="tablist" aria-label="Khu vực quản trị">{([['overview', 'Tổng quan'], ['sync', 'Đồng bộ'], ['quality', 'Chất lượng dữ liệu'], ['performance', 'Hiệu năng']] as const).map(([key, label]) => <Button key={key} role="tab" aria-selected={tab === key} className={tab === key ? '' : 'secondary'} onClick={() => setTab(key)}>{label}</Button>)}</div>
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}
    {tab === 'overview' && <><section className="card"><h2>Hoạt động</h2><div className="kpi-grid">{metrics.map(([key, label]) => <article className="card" key={key}><small>{label}</small><strong>{fmt(stats[key])}</strong></article>)}</div></section><section className="card"><h2>Trạng thái triển khai</h2><div className="kpi-grid">{([['environment', 'Môi trường'], ['version', 'Phiên bản'], ['database', 'Database'], ['storage', 'Lưu trữ'], ['source', 'Nguồn e-GP'], ['queue_length', 'Job chờ'], ['recent_5xx', 'Lỗi 5xx gần đây']] as const).map(([key, label]) => <article className="card" key={key}><small>{label}</small><strong>{fmt(production[key])}</strong></article>)}</div></section></>}
    {tab === 'sync' && <><section className="card"><h2>Nguồn dữ liệu</h2><p>{sources.length ? sources.map(source => `${source.name}: ${source.is_enabled ? 'đang bật' : 'tạm dừng'}`).join(' · ') : 'Chưa có nguồn đồng bộ.'}</p><div className="form-actions"><Button disabled={busy} onClick={() => void action('/api/data-sync/runs', { mode: 'stale', limit: 100 })}>Tạo lượt đồng bộ</Button><Button disabled={busy} className="secondary" onClick={() => void action('/api/data-sync/process', { limit: 5 })}>Xử lý hàng đợi</Button>{sources.map(source => <Button key={source.id} disabled={busy} className="secondary" onClick={() => void action(`/api/data-sync/sources/${encodeURIComponent(source.id)}/${source.is_enabled ? 'pause' : 'enable'}`, {})}>{source.is_enabled ? 'Tạm dừng' : 'Bật'} {source.name}</Button>)}</div><form onSubmit={event => { event.preventDefault(); if (code.trim()) void action('/api/data-sync/force', { entity_id: code.trim() }); }}><label>Mã cần đồng bộ lại <Input value={code} onChange={event => setCode(event.target.value)} placeholder="Mã TBMT hoặc KHLCNT" /></label><Button disabled={busy || !code.trim()}>Đồng bộ mã</Button></form></section><section className="card"><h2>Hàng đợi</h2>{jobs.length ? <div className="table-scroll"><Table><TableHeader><TableRow><TableHead>Mã</TableHead><TableHead>Loại</TableHead><TableHead>Trạng thái</TableHead><TableHead>Số lần thử</TableHead><TableHead>Thao tác</TableHead></TableRow></TableHeader><TableBody>{jobs.map(job => <TableRow key={job.id}><TableCell>{job.entity_id}</TableCell><TableCell>{job.job_type}</TableCell><TableCell title={job.last_error}>{job.status}</TableCell><TableCell>{job.attempts}</TableCell><TableCell>{job.status === 'failed' && <Button disabled={busy} onClick={() => void action(`/api/data-sync/jobs/${job.id}/retry`, {})}>Thử lại</Button>}{['queued', 'pending', 'retry', 'retrying'].includes(job.status) && <Button disabled={busy} className="secondary" onClick={() => void action(`/api/data-sync/jobs/${job.id}/cancel`, {}, 'Hủy job đang chờ?')}>Hủy</Button>}</TableCell></TableRow>)}</TableBody></Table></div> : <p>Hàng đợi đang trống.</p>}</section></>}
    {tab === 'users' && <AdminUsersPanel key={revision}/>}
    {tab === 'quality' && <QualityPanel/>}
    {tab === 'performance' && <><section className="card"><h2>Hiệu năng instance</h2><p>Số liệu trong bộ nhớ của instance đang phục vụ.</p><div className="kpi-grid">{([['request_count', 'Yêu cầu'], ['error_count_5xx', 'Lỗi 5xx'], ['p50_ms', 'p50 (ms)'], ['p95_ms', 'p95 (ms)'], ['queue_length', 'Job chờ']] as const).map(([key, label]) => <article className="card" key={key}><small>{label}</small><strong>{fmt(performance[key])}</strong></article>)}</div></section><section className="card"><h2>Theo đường dẫn</h2>{routes.length ? <div className="table-scroll"><Table><TableHeader><TableRow><TableHead>Đường dẫn</TableHead><TableHead>Lượt</TableHead><TableHead>p50</TableHead><TableHead>p95</TableHead><TableHead>Lỗi 5xx</TableHead></TableRow></TableHeader><TableBody>{routes.map(route => <TableRow key={route.route}><TableCell>{route.route}</TableCell><TableCell>{route.count}</TableCell><TableCell>{route.p50_ms} ms</TableCell><TableCell>{route.p95_ms} ms</TableCell><TableCell>{route.errors_5xx}</TableCell></TableRow>)}</TableBody></Table></div> : <p>Chưa có yêu cầu trên instance này.</p>}</section></>}
  </main>;
}
