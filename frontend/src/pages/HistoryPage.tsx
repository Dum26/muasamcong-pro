import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { workspaceApi } from '../api/core';
import { dateTime } from '../lib/format';
import { searchToUrl } from '../lib/searchUrl';
import type { HistoryItem, SearchParams } from '../types';
import { toast } from 'sonner';
import { Pin } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { EmptyState } from '@/components/shared/EmptyState';

export function replayParams(item: HistoryItem): SearchParams {
  return {
    mode: item.mode === 'Kế hoạch lựa chọn nhà thầu' ? item.mode : 'Thông báo mời thầu',
    keyword: item.keyword || '', use_dates: item.use_dates !== false,
    date_from: item.date_from || '', date_to: item.date_to || '',
    status: item.status || 'Tất cả trạng thái', pages: item.pages || 2,
    detail: item.detail === true, fast_mode: item.fast_mode !== false,
    remove_duplicates: item.remove_duplicates !== false,
    bid_form: item.bid_form || '', location: item.location || '',
  };
}

export function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [renameItem, setRenameItem] = useState<HistoryItem | null>(null);
  const [deleteItem, setDeleteItem] = useState<HistoryItem | null>(null);
  const [title, setTitle] = useState('');
  const navigate = useNavigate();
  useEffect(() => { void workspaceApi.history().then(data => setItems(data.items)).catch(caught => setError(String(caught))).finally(() => setLoading(false)); }, []);
  async function action(item: HistoryItem, name: 'pin' | 'rename' | 'delete', nextTitle?: string) {
    try { setItems((await workspaceApi.historyAction({ action: name, id: item.id, name: nextTitle, pinned: !item.pinned })).items); setRenameItem(null); setDeleteItem(null); toast.success(name === 'delete' ? 'Đã xóa truy vấn.' : 'Đã cập nhật truy vấn.'); }
    catch (caught) { const message = String(caught); setError(message); toast.error(message); }
  }
  function replay(item: HistoryItem) {
    if (item.mode === 'Kho dữ liệu') { const params = new URLSearchParams(); for (const [key, value] of Object.entries(item)) if (typeof value === 'string' && value && !['id', 'name', 'mode', 'created_at', 'time'].includes(key)) params.set(key === 'keyword' ? 'q' : key, value); params.set('run', '1'); navigate('/app/archive?' + params); return; }
    const url = searchToUrl(replayParams(item)); url.set('run', '1');
    navigate('/app/search?' + url.toString());
  }
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">LỊCH SỬ</p><h1>Truy vấn gần đây</h1></div></div>
    {error && <p role="alert" className="error">{error}</p>}
    {loading ? <div className="grid gap-3"><Skeleton className="h-24"/><Skeleton className="h-24"/></div> : !items.length ? <EmptyState title="Chưa có truy vấn" description="Lịch sử tra cứu sẽ xuất hiện tại đây." action={<Button asChild><Link to="/app/search">Bắt đầu tra cứu</Link></Button>}/> : <div className="grid gap-3">{items.map(item => <Card key={item.id}><CardContent className="flex flex-wrap items-center justify-between gap-4"><div className="min-w-0"><strong className="flex items-center gap-2">{item.pinned && <Pin size={14} aria-label="Đã ghim"/>}{item.name || item.keyword || 'Tìm theo ngày'}</strong><p className="text-sm text-muted-foreground">{item.mode || 'TBMT'} · {item.date_from || '—'} → {item.date_to || '—'} · {item.result_count ?? '—'} kết quả · {dateTime(item.created_at || item.time)}</p></div><div className="flex flex-wrap gap-2"><Button size="sm" onClick={() => replay(item)}>Chạy lại</Button><Button size="sm" variant="outline" onClick={() => void action(item, 'pin')}>{item.pinned ? 'Bỏ ghim' : 'Ghim'}</Button><Button size="sm" variant="outline" onClick={() => { setRenameItem(item); setTitle(item.name || item.keyword || ''); }}>Đổi tên</Button><Button size="sm" variant="destructive" onClick={() => setDeleteItem(item)}>Xóa</Button></div></CardContent></Card>)}</div>}
    <Dialog open={!!renameItem} onOpenChange={open => { if (!open) setRenameItem(null); }}><DialogContent><DialogHeader><DialogTitle>Đổi tên truy vấn</DialogTitle><DialogDescription>Đặt tên dễ nhớ cho lần tra cứu này.</DialogDescription></DialogHeader><form onSubmit={event => { event.preventDefault(); if (renameItem && title.trim()) void action(renameItem, 'rename', title.trim()); }}><Input autoFocus aria-label="Tên truy vấn" maxLength={80} value={title} onChange={event => setTitle(event.target.value)}/><DialogFooter className="mt-4"><Button type="button" variant="outline" onClick={() => setRenameItem(null)}>Hủy</Button><Button disabled={!title.trim()}>Lưu</Button></DialogFooter></form></DialogContent></Dialog>
    <AlertDialog open={!!deleteItem} onOpenChange={open => { if (!open) setDeleteItem(null); }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Xóa truy vấn?</AlertDialogTitle><AlertDialogDescription>Lịch sử tra cứu này sẽ bị xóa.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Giữ lại</AlertDialogCancel><AlertDialogAction onClick={() => { if (deleteItem) void action(deleteItem, 'delete'); }}>Xóa</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </main>;
}
