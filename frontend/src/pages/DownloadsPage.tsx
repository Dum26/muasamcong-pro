import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { workspaceApi } from '../api/core';
import { downloadGet } from '../api/client';
import { dateTime } from '../lib/format';
import type { DownloadItem } from '../types';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/shared/EmptyState';

export function DownloadsPage() {
  const [items, setItems] = useState<DownloadItem[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  async function load() { try { setItems((await workspaceApi.downloads()).items); setError(''); } catch (caught) { setError(String(caught)); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  async function download(item: DownloadItem) {
    if (!item.url) return;
    try { await downloadGet(item.url, item.name); toast.success('Đã tải file.'); }
    catch (caught) { const message = String(caught); setError(message); toast.error(message); }
  }
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">TẢI XUỐNG</p><h1>File đã xuất</h1><p>File lưu lại theo tài khoản; liên kết có thể hết hạn.</p></div></div>
    {error && <p role="alert" className="error">Không lấy được dữ liệu: {error} <Button variant="outline" size="sm" onClick={() => void load()}>Thử lại</Button></p>}
    {loading ? <div className="grid gap-3"><Skeleton className="h-24"/><Skeleton className="h-24"/></div> : !items.length ? <EmptyState title="Chưa có file đã xuất" description="Xuất Excel từ Tra cứu hoặc Phân tích, file sẽ xuất hiện tại đây."/> : <div className="grid gap-3">{items.map(item => <Card key={item.id}><CardContent className="flex items-start justify-between gap-4"><div className="min-w-0 space-y-1"><strong className="break-all">{item.name}</strong><div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground"><span>{item.kind}</span><span>{dateTime(item.time)}</span><span>{item.size === null ? '—' : `${(item.size / 1048576).toFixed(2)} MB`}</span><Badge variant={item.status === 'Hoàn thành' ? 'secondary' : 'outline'}>{item.status}</Badge></div>{item.error && <p className="text-sm text-destructive">{item.error}</p>}</div>{item.url && <Button variant="outline" size="sm" onClick={() => void download(item)}>Tải lại</Button>}</CardContent></Card>)}</div>}
  </main>;
}
