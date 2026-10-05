import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import { workspaceApi } from '../api/core';
import { dateTime } from '../lib/format';
import type { Notification } from '../types';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/shared/EmptyState';

export function NotificationsPage() {
  const [items, setItems] = useState<Notification[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  async function load() { try { setItems((await workspaceApi.notifications()).items); setError(''); } catch (caught) { setError(String(caught)); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  async function read(id?: string) {
    try { await workspaceApi.notificationAction({ action: id ? 'read' : 'read-all', ...(id ? { id } : {}) }); await load(); toast.success('Đã đánh dấu đã đọc.'); }
    catch (caught) { const message = String(caught); setError(message); toast.error(message); }
  }
  const unread = items.filter(item => !item.is_read).length;
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">THÔNG BÁO</p><h1>Cập nhật của bạn</h1><p>{unread} chưa đọc</p></div><Button disabled={!unread} onClick={() => void read()}>Đánh dấu đã đọc</Button></div>
    {error && <p role="alert" className="error">Không lấy được dữ liệu: {error} <Button variant="outline" size="sm" onClick={() => void load()}>Thử lại</Button></p>}
    {loading ? <div className="grid gap-3"><Skeleton className="h-24"/><Skeleton className="h-24"/></div> : !items.length ? <EmptyState title="Chưa có thông báo" description="Cập nhật về các gói đang theo dõi sẽ xuất hiện tại đây."/> : <div className="grid gap-3">{items.map(item => <Card key={item.id} className={item.is_read ? '' : 'border-primary/40'}><CardContent className="flex items-start justify-between gap-4"><div className="min-w-0 space-y-1"><div className="flex items-center gap-2"><strong>{item.title}</strong>{!item.is_read && <Badge variant="secondary">Mới</Badge>}</div><p className="text-sm text-muted-foreground">{item.message}</p><small>{dateTime(item.created_at)}</small>{item.tender_code && <div><Link to={`/app/tenders/${encodeURIComponent(item.tender_code)}`}>{item.tender_code}</Link></div>}</div>{!item.is_read && <Button variant="outline" size="sm" onClick={() => void read(item.id)}>Đã đọc</Button>}</CardContent></Card>)}</div>}
  </main>;
}
