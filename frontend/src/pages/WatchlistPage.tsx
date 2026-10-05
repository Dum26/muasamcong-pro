import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { Pin } from 'lucide-react';
import { toast } from 'sonner';
import { workspaceApi } from '../api/core';
import type { WatchItem } from '../types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog';
import { EmptyState } from '@/components/shared/EmptyState';

const statuses = ['Mới', 'Đang xem', 'Quan tâm', 'Đang xử lý', 'Hoàn tất', 'Bỏ qua'];
const priorities = ['Thấp', 'Trung bình', 'Cao', 'Khẩn cấp'];

export function WatchlistPage() {
  const [items, setItems] = useState<WatchItem[]>([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => { void workspaceApi.watchlist().then(data => setItems(data.items)).catch(caught => setError(String(caught))).finally(() => setLoading(false)); }, []);
  async function update(item: WatchItem, body: object) {
    try { setItems((await workspaceApi.watch({ action: 'edit', code: item.code, ...body })).items); }
    catch (caught) { const message = String(caught); setError(message); toast.error(message); }
  }
  async function remove(item: WatchItem) {
    try { setItems((await workspaceApi.watch({ action: 'remove', code: item.code })).items); toast.success('Đã bỏ theo dõi.'); }
    catch (caught) { const message = String(caught); setError(message); toast.error(message); }
  }
  const visible = items.filter(item => `${item.code} ${item.name} ${item.investor}`.toLocaleLowerCase('vi').includes(query.toLocaleLowerCase('vi')));
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">THEO DÕI</p><h1>Gói thầu của tôi</h1><p>{items.length} gói đang theo dõi</p></div><Button asChild><Link to="/app/search">Tra cứu thêm</Link></Button></div>
    <Card className="mb-4"><CardContent><Label htmlFor="watchlist-search">Tìm trong danh sách</Label><Input id="watchlist-search" className="mt-2" value={query} onChange={event => setQuery(event.target.value)} placeholder="Mã, tên hoặc chủ đầu tư"/></CardContent></Card>
    {error && <p role="alert" className="error">{error}</p>}
    {loading ? <div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-64"/><Skeleton className="h-64"/></div> : !visible.length ? <EmptyState title="Chưa có gói phù hợp" description="Tra cứu và theo dõi gói thầu để quản lý tại đây." action={<Button asChild variant="outline"><Link to="/app/search">Tra cứu gói thầu</Link></Button>}/> :
      <div className="grid gap-4 md:grid-cols-2">{visible.map(item => <Card key={item.code}><CardHeader className="flex flex-row items-start justify-between gap-3"><div className="min-w-0"><CardTitle><Link to={`/app/tenders/${encodeURIComponent(item.code)}`}>{item.name || item.code}</Link></CardTitle><p className="mt-1 text-sm text-muted-foreground">{item.code} · {item.investor || 'Chưa có chủ đầu tư'}</p></div><Button variant="ghost" size="icon" aria-label={item.pinned ? `Bỏ ghim ${item.code}` : `Ghim ${item.code}`} aria-pressed={item.pinned} onClick={() => void update(item, { pinned: !item.pinned })}><Pin className={item.pinned ? 'fill-primary text-primary' : ''}/></Button></CardHeader>
        <CardContent className="grid gap-4"><div className="flex items-center justify-between gap-3"><small>Đóng thầu: {item.deadline || 'Chưa có'}</small>{item.has_update && <Badge variant="secondary">Có cập nhật mới</Badge>}</div>
          <div className="grid gap-3 sm:grid-cols-2"><div className="grid gap-2"><Label htmlFor={`status-${item.code}`}>Trạng thái</Label><Select value={item.workflow_status} onValueChange={value => void update(item, { workflow_status: value })}><SelectTrigger id={`status-${item.code}`}><SelectValue placeholder="Chọn trạng thái"/></SelectTrigger><SelectContent>{statuses.map(status => <SelectItem key={status} value={status}>{status}</SelectItem>)}</SelectContent></Select></div>
            <div className="grid gap-2"><Label htmlFor={`priority-${item.code}`}>Ưu tiên</Label><Select value={item.priority} onValueChange={value => void update(item, { priority: value })}><SelectTrigger id={`priority-${item.code}`}><SelectValue placeholder="Chọn ưu tiên"/></SelectTrigger><SelectContent>{priorities.map(priority => <SelectItem key={priority} value={priority}>{priority}</SelectItem>)}</SelectContent></Select></div></div>
          <div className="grid gap-2"><Label htmlFor={`note-${item.code}`}>Ghi chú</Label><Textarea id={`note-${item.code}`} defaultValue={item.note} onBlur={event => { if (event.target.value !== item.note) void update(item, { note: event.target.value }); }}/></div>
          <div className="grid gap-2"><Label htmlFor={`tags-${item.code}`}>Tag, cách nhau bằng dấu phẩy</Label><Input id={`tags-${item.code}`} defaultValue={item.tags.join(', ')} onBlur={event => { const tags = event.target.value.split(',').map(tag => tag.trim()).filter(Boolean); if (tags.join(',') !== item.tags.join(',')) void update(item, { tags }); }}/></div>
          <AlertDialog><AlertDialogTrigger asChild><Button variant="destructive" className="justify-self-start">Bỏ theo dõi</Button></AlertDialogTrigger><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Bỏ theo dõi {item.code}?</AlertDialogTitle><AlertDialogDescription>Gói thầu sẽ không còn trong danh sách theo dõi của bạn.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Giữ lại</AlertDialogCancel><AlertDialogAction onClick={() => void remove(item)}>Bỏ theo dõi</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
        </CardContent></Card>)}</div>}
  </main>;
}
