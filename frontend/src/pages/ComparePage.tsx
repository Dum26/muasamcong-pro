import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router';
import { request } from '../api/client';

interface Comparison { fields: string[]; items: Array<Record<string, string | number | null>> }
const labels: Record<string, string> = { tender_code: 'Mã TBMT', title: 'Tên gói', investor_name: 'Chủ đầu tư', package_price: 'Giá gói', bid_closing_date: 'Đóng thầu', selection_method: 'Hình thức LCNT', status: 'Trạng thái', winning_contractor: 'Nhà thầu trúng', winning_price: 'Giá trúng', saving_rate: 'Tỷ lệ tiết kiệm' };
export function ComparePage() {
  const location = useLocation();
  const initial = (location.state as { codes?: string[] } | null)?.codes || [];
  const [input, setInput] = useState(initial.join(', ')); const [data, setData] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(false); const [error, setError] = useState('');
  async function compare(event: FormEvent) { event.preventDefault(); const codes = [...new Set(input.split(/[\s,;]+/).map(value => value.trim().toUpperCase()).filter(Boolean))];
    if (codes.length < 2 || codes.length > 5) { setError('Chọn từ 2 đến 5 mã TBMT.'); return; }
    const params = new URLSearchParams(); codes.forEach(code => params.append('code', code));
    setLoading(true); setError(''); setData(null);
    try { setData(await request<Comparison>(`/api/intelligence/compare?${params}`)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { setLoading(false); }
  }
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">SO SÁNH</p><h1>Đặt các gói thầu cạnh nhau</h1><p>So sánh 2–5 TBMT đã thu thập. Trường chưa có dữ liệu được ghi rõ.</p></div><Link to="/app/archive">Kho dữ liệu</Link></div><form className="card" onSubmit={event => void compare(event)}><label>Mã TBMT, cách nhau bằng dấu phẩy<Textarea rows={3} value={input} onChange={event => setInput(event.target.value)} placeholder="IB2600…, IB2600…"/></label><Button disabled={loading}>{loading ? 'Đang so sánh…' : 'So sánh'}</Button></form>{error && <p role="alert" className="error">{error}</p>}{loading && <div className="card skeleton"/>}{data && <section className="card"><h2>{data.items.length} gói</h2><div className="table-scroll"><Table><TableHeader><TableRow><TableHead>Thông tin</TableHead>{data.items.map((item, index) => <TableHead key={index}><Link to={`/app/tenders/${encodeURIComponent(String(item.tender_code || ''))}`}>{item.tender_code}</Link></TableHead>)}</TableRow></TableHeader><TableBody>{data.fields.map(field => <TableRow key={field}><TableHead scope="row">{labels[field] || field}</TableHead>{data.items.map((item, index) => <TableCell key={index}>{String(item[field] ?? 'Chưa có dữ liệu')}</TableCell>)}</TableRow>)}</TableBody></Table></div></section>}</main>;
}
