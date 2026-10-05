import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router';
import { workspaceApi } from '../api/core';
import { tenderCode } from '../lib/format';
import type { PlanDetailResponse, Tender, TenderDetailResponse } from '../types';
import { Copy, ExternalLink, RefreshCw, Star } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';

export function previewDetail(row: Tender): TenderDetailResponse {
  return { tender: { tender_code: tenderCode(row), khlcnt_code: row.plan_no || row.plan_reference || null,
    title: row.package_name || row.plan_name, investor_name: row.investor_name, procuring_entity_name: row.procuring_entity_name,
    package_price: row.package_price, winning_price: row.winning_price, publish_date: row.public_date,
    bid_closing_date: row.bid_close_date, status: row.tender_status, selection_method: row.bid_form,
    location: row.location, winning_contractor: row.winner, source_url: row.source_url,
    data_health: 'Xem nhanh từ kết quả tra cứu', last_synced_at: null },
    timeline: [], changes: [], documents: [], related: [] };
}

export function TenderPage() {
  const { code = '' } = useParams(); const [data, setData] = useState<TenderDetailResponse | null>(null);
  const location = useLocation();
  const preview = (location.state as { row?: Tender } | null)?.row;
  const [plan, setPlan] = useState<PlanDetailResponse | null>(null);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [watched, setWatched] = useState(false); const [revision, setRevision] = useState(0);
  useEffect(() => { let live = true;
    void workspaceApi.watchlist().then(result => { if (live) setWatched(result.items.some(item => item.code === code)); }).catch(() => {});
    return () => { live = false; };
  }, [code]);
  useEffect(() => { let live = true; setData(null); setPlan(null); setError('');
    void (code.startsWith('PL') ? workspaceApi.plan(code).then(result => { if (live) setPlan(result); }) :
      workspaceApi.tender(code).then(result => { if (live) setData(result); }))
      .catch(caught => { if (!live) return;
        if (preview && tenderCode(preview) === code) {
          if (code.startsWith('PL')) setPlan({ plan: { plan_code: code, title: preview.plan_name || preview.package_name, investor_name: preview.investor_name, publish_date: preview.public_date }, package_count: 0, packages: [] });
          else setData(previewDetail(preview));
        } else setError(caught instanceof Error ? caught.message : 'Không lấy được chi tiết.');
      });
    return () => { live = false; };
  }, [code, preview, revision]);
  const tender = data?.tender;
  async function follow() { if (!tender && !plan) return; setBusy(true);
    try { const result = await workspaceApi.watch({ action: watched ? 'remove' : 'add', code, name: tender?.title || plan?.plan.title,
      investor: tender?.investor_name || plan?.plan.investor_name, deadline: tender?.bid_closing_date,
      url: tender?.source_url, row: { package_name: tender?.title || plan?.plan.title,
        investor_name: tender?.investor_name || plan?.plan.investor_name,
        bid_close_date: tender?.bid_closing_date, tender_status: tender?.status } }); setWatched(result.items.some(item => item.code === code)); toast.success(watched ? `Đã bỏ theo dõi ${code}.` : `Đã theo dõi ${code}.`); }
    catch (caught) { const message = caught instanceof Error ? caught.message : 'Không theo dõi được.'; setError(message); toast.error(message); }
    finally { setBusy(false); }
  }
  const facts = tender ? [
    ['Mã TBMT', tender.tender_code], ['KHLCNT', tender.khlcnt_code], ['Tên gói', tender.title],
    ['Chủ đầu tư', tender.investor_name], ['Bên mời thầu', tender.procuring_entity_name],
    ['Giá gói thầu', tender.package_price], ['Ngày đăng', tender.publish_date],
    ['Đóng thầu', tender.bid_closing_date], ['Địa điểm', tender.location],
    ['Trạng thái', tender.status], ['Nhà thầu trúng', tender.winning_contractor],
    ['Giá trúng', tender.winning_price], ['Hình thức LCNT', tender.selection_method],
  ] : [];
  return <main className="page"><div className="page-heading"><div className="min-w-0"><Link to="/app/search">← Tra cứu</Link><h1 className="mt-2 max-w-4xl break-words">{tender?.title || plan?.plan.title || `Chi tiết ${code}`}</h1><p className="flex flex-wrap items-center gap-2"><span>{code}</span>{tender?.status && <Badge variant="secondary">{tender.status}</Badge>}{watched && <Badge variant="outline">Đang theo dõi</Badge>}</p></div><div className="form-actions"><Button disabled={(!tender && !plan) || busy} variant={watched ? 'outline' : 'default'} onClick={() => void follow()}><Star size={16} className={watched ? 'fill-current' : ''}/> {watched ? 'Bỏ theo dõi' : 'Theo dõi'}</Button><Button variant="outline" onClick={() => { setRevision(value => value + 1); }} aria-label="Tải lại chi tiết"><RefreshCw size={16}/> Tải lại</Button><Button variant="outline" onClick={() => void navigator.clipboard.writeText(code).then(() => toast.success('Đã sao chép mã.')).catch(() => toast.error('Không sao chép được mã.'))}><Copy size={16}/> Sao chép mã</Button>{tender?.source_url?.startsWith('https://muasamcong.mpi.gov.vn/') && <Button asChild variant="outline"><a href={tender.source_url} target="_blank" rel="noopener noreferrer"><ExternalLink size={16}/> Mở nguồn</a></Button>}</div></div>
    {error && <p role="alert" className="error">{error} <Button variant="outline" size="sm" onClick={() => setRevision(value => value + 1)}>Thử lại</Button></p>}{!tender && !plan && !error && <Skeleton className="h-64" aria-label="Đang tải chi tiết"/>}
    {plan && <section className="card"><h2>{plan.plan.title || code}</h2><p>KHLCNT · Chủ đầu tư: {plan.plan.investor_name || 'Chưa có dữ liệu'} · Ngày đăng: {plan.plan.publish_date || '—'}</p><h3>{plan.package_count} gói liên kết</h3><div className="item-list">{plan.packages.map(item => <Link className="list-item" key={item.tender_code} to={`/app/tenders/${item.tender_code}`}>{item.title || item.tender_code}</Link>)}</div></section>}
    {tender && <><section className="card"><h2>Thông tin chung</h2><div className="facts">{facts.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value || 'Chưa có dữ liệu'}</strong></div>)}</div><p>Cập nhật: {tender.last_synced_at || 'Chưa đồng bộ'} · {tender.data_health}</p></section><section className="card"><h2>Tiến độ gói thầu</h2>{data?.timeline.length ? <div className="item-list">{data.timeline.map((event, index) => <div className="list-item" key={index}><strong>{event.event_type}</strong><span>{event.description || ''} · {event.event_at}</span></div>)}</div> : <p>Chưa có sự kiện nguồn.</p>}{tender.winning_contractor && <p>Nhà thầu trúng: {tender.winning_contractor}</p>}</section><section className="card"><h2>Tài liệu</h2>{data?.documents.length ? <div className="item-list">{data.documents.map(item => <Link className="list-item" key={item.id} to={`/app/documents/egp/${encodeURIComponent(item.id)}`}><strong>{item.filename || item.id}</strong><span>{item.status}</span></Link>)}</div> : <p>Chưa có tài liệu đã thu thập.</p>}<Link to="/app/documents">Mở Trung tâm tài liệu</Link></section><section className="card"><h2>Lịch sử thay đổi</h2>{data?.changes.length ? <div className="table-scroll"><Table><TableHeader><TableRow>{['Thời gian', 'Trường', 'Trước', 'Sau'].map(label => <TableHead key={label}>{label}</TableHead>)}</TableRow></TableHeader><TableBody>{data.changes.map((item, index) => <TableRow key={index}><TableCell>{item.detected_at}</TableCell><TableCell>{item.field_name}</TableCell><TableCell>{item.old_value || '—'}</TableCell><TableCell>{item.new_value || '—'}</TableCell></TableRow>)}</TableBody></Table></div> : <p>Chưa ghi nhận thay đổi.</p>}</section><section className="card"><h2>Gói liên quan</h2>{data?.related.length ? <div className="item-list">{data.related.map(item => <Link className="list-item" key={item.tender_code} to={`/app/tenders/${encodeURIComponent(item.tender_code)}`}><strong>{item.title || item.tender_code}</strong><small>{item.tender_code} · {item.reason}</small></Link>)}</div> : <p>Chưa có gói liên quan.</p>}</section><section className="card"><h2>Ghi chú và phân tích</h2><p>Ghi chú được lưu trong danh sách theo dõi của tài khoản.</p><div className="form-actions"><Link className="button secondary" to="/app/watchlist">Mở Theo dõi</Link><Link className="button secondary" to="/app/ai">AI Hồ sơ</Link><Link className="button secondary" to="/app/codes" state={{ text: code }}>Tra cứu mã</Link></div></section></>}
  </main>;
}
