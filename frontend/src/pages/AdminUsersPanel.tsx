import { useEffect, useState } from 'react';
import { Users, UserCheck, LockKeyhole, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useConfirm } from '@/components/shared/ConfirmProvider';
import { post, request } from '../api/client';

type Account = { id: string; email: string; role: string; is_active: boolean; created_at: string; last_login_at: string | null };
type Directory = { items: Account[]; total: number; page: number; page_size: number; summary: { total: number; active: number; locked: number; admins: number } };
const date = (value: string | null) => value ? new Date(value).toLocaleString('vi-VN') : 'Chưa đăng nhập';
const counters = [
  ['total', 'Tổng người dùng', Users], ['active', 'Tài khoản được mở', UserCheck],
  ['locked', 'Tài khoản đã khóa', LockKeyhole], ['admins', 'Quản trị viên', ShieldCheck],
] as const;

export function AdminUsersPanel() {
  const confirm = useConfirm();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [role, setRole] = useState('');
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<Directory | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ q: query, status, role, page: String(page) });
      void request<Directory>(`/api/admin/users?${params}`, { signal: controller.signal })
        .then(value => { if (!controller.signal.aborted) setData(value); })
        .catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Không tải được danh sách.'); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, status, role, page, revision]);
  async function toggle(account: Account) {
    if (!await confirm(`${account.is_active ? 'Khóa' : 'Mở khóa'} tài khoản ${account.email}?${account.is_active ? ' Các phiên đăng nhập hiện tại sẽ bị thu hồi.' : ''}`)) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await post('/api/admin/users/status', { id: account.id, is_active: !account.is_active });
      setNotice(`Đã ${account.is_active ? 'khóa' : 'mở khóa'} tài khoản ${account.email}.`);
      setRevision(value => value + 1);
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Không cập nhật được tài khoản.'); }
    finally { setBusy(false); }
  }
  return <section className="mt-6 space-y-5" aria-label="Quản lý người dùng">
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{counters.map(([key, label, Icon]) => <article key={key} className="rounded-xl border bg-card p-5"><div className="flex items-center justify-between gap-3 text-muted-foreground"><span className="text-sm">{label}</span><Icon size={19}/></div><strong className="mt-3 block text-3xl tabular-nums">{data ? data.summary[key].toLocaleString('vi-VN') : '—'}</strong></article>)}</div>
    <div className="rounded-xl border bg-card p-5">
      <h2>Danh sách tài khoản</h2><p className="mb-5 text-sm text-muted-foreground">Xem số lượng, vai trò và lần đăng nhập gần nhất. Khóa tài khoản sẽ giữ nguyên dữ liệu của người dùng.</p>
      <div className="mb-5 grid gap-3 md:grid-cols-3">
        <label>Tìm email<Input value={query} placeholder="Nhập email người dùng…" onChange={event => { setQuery(event.target.value); setPage(1); }}/></label>
        <label>Trạng thái<select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="">Tất cả trạng thái</option><option value="active">Được mở</option><option value="locked">Đã khóa</option></select></label>
        <label>Vai trò<select value={role} onChange={event => { setRole(event.target.value); setPage(1); }}><option value="">Tất cả vai trò</option><option value="admin">Quản trị viên</option><option value="user">Người dùng</option></select></label>
      </div>
      {error && <div role="alert" className="error mb-4">{error} <Button variant="outline" onClick={() => setRevision(value => value + 1)}>Thử lại</Button></div>}
      {notice && <p role="status" className="mb-4 text-sm text-primary">{notice}</p>}
      <div aria-busy={loading}>
        {loading ? <div role="status" className="rounded-lg bg-muted p-8 text-center text-muted-foreground">Đang tải người dùng…</div> : !error && data && <>
          <div className="table-scroll"><Table><TableHeader><TableRow><TableHead>Email</TableHead><TableHead>Vai trò</TableHead><TableHead>Trạng thái</TableHead><TableHead>Ngày tạo</TableHead><TableHead>Đăng nhập gần nhất</TableHead><TableHead>Thao tác</TableHead></TableRow></TableHeader><TableBody>
            {data.items.map(account => <TableRow key={account.id}><TableCell className="font-medium">{account.email}</TableCell><TableCell>{account.role === 'admin' ? 'Quản trị viên' : 'Người dùng'}</TableCell><TableCell><span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${account.is_active ? 'bg-accent text-accent-foreground' : 'bg-muted text-muted-foreground'}`}>{account.is_active ? 'Được mở' : 'Đã khóa'}</span></TableCell><TableCell>{date(account.created_at)}</TableCell><TableCell>{date(account.last_login_at)}</TableCell><TableCell>{account.role === 'admin' ? <span className="text-xs text-muted-foreground">Được bảo vệ</span> : <Button variant="outline" size="sm" disabled={busy} onClick={() => void toggle(account)}>{account.is_active ? 'Khóa tài khoản' : 'Mở khóa'}</Button>}</TableCell></TableRow>)}
            {!data.items.length && <TableRow><TableCell colSpan={6} className="py-10 text-center text-muted-foreground">Không tìm thấy tài khoản phù hợp.</TableCell></TableRow>}
          </TableBody></Table></div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm"><span>{data.total.toLocaleString('vi-VN')} tài khoản · Trang {data.page}/{Math.max(1, Math.ceil(data.total / data.page_size))}</span><div className="flex gap-2"><Button variant="outline" disabled={busy || data.page <= 1} onClick={() => setPage(data.page - 1)}>Trước</Button><Button variant="outline" disabled={busy || data.page * data.page_size >= data.total} onClick={() => setPage(data.page + 1)}>Sau</Button></div></div>
        </>}
      </div>
    </div>
  </section>;
}
