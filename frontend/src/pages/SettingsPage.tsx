import { useState, type Dispatch, type SetStateAction } from 'react';
import { useOutletContext } from 'react-router';
import { downloadDirectoryName, setDownloadDirectory } from '../api/client';
import { post } from '../api/client';
import { useAuth } from '../app/AuthProvider';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface ShellSettings {
  dark: boolean; setDark: Dispatch<SetStateAction<boolean>>;
  collapsed: boolean; setCollapsed: Dispatch<SetStateAction<boolean>>;
}

export function SettingsPage() {
  const { user } = useAuth();
  const { dark, setDark, collapsed, setCollapsed } = useOutletContext<ShellSettings>();
  const [folder, setFolder] = useState(downloadDirectoryName());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  async function chooseFolder() {
    const picker = (window as Window & { showDirectoryPicker?: () => Promise<FileSystemDirectoryHandle> }).showDirectoryPicker;
    if (!picker) { setError('Trình duyệt này chưa hỗ trợ chọn thư mục. File sẽ vào thư mục Tải xuống.'); return; }
    try { const handle = await picker.call(window); setDownloadDirectory(handle); setFolder(handle.name); setError(''); }
    catch (caught) { if (caught instanceof Error && caught.name !== 'AbortError') setError(caught.message); }
  }
  async function importLegacy() {
    setBusy(true); setError(''); setMessage('');
    try {
      let history: unknown = [];
      try { history = JSON.parse(localStorage.getItem('msc_recent') || '[]'); } catch { /* old data may be malformed */ }
      const result = await post<{ watchlist: number; presets: number; history: number }>('/api/import-legacy', {
        history: Array.isArray(history) ? history.slice(0, 100) : [],
      });
      setMessage(`Đã nhập ${result.watchlist} gói theo dõi, ${result.presets} bộ lọc và ${result.history} truy vấn.`);
    } catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">CÀI ĐẶT</p><h1>Bàn làm việc của tôi</h1><p>Tùy chỉnh cách hiển thị và tải dữ liệu.</p></div></div>
    {error && <p role="alert" className="error">{error}</p>}{message && <p role="status">{message}</p>}
    <Tabs defaultValue="account"><TabsList><TabsTrigger value="account">Tài khoản & giao diện</TabsTrigger><TabsTrigger value="downloads">Tải xuống</TabsTrigger><TabsTrigger value="data">Dữ liệu cũ</TabsTrigger></TabsList>
      <TabsContent value="account" className="grid gap-4 pt-4"><Card><CardHeader><CardTitle>Tài khoản</CardTitle></CardHeader><CardContent><p>{user?.email}</p><small>Vai trò: {user?.role === 'admin' ? 'Quản trị' : 'Thành viên'}</small></CardContent></Card>
        <Card><CardHeader><CardTitle>Giao diện</CardTitle></CardHeader><CardContent className="grid gap-4"><div className="flex items-center justify-between gap-4"><label htmlFor="dark-mode">Chế độ tối</label><Switch id="dark-mode" checked={dark} onCheckedChange={setDark}/></div><div className="flex items-center justify-between gap-4"><span>Thanh điều hướng</span><Button variant="outline" onClick={() => { localStorage.setItem('msc_react_sidebar', collapsed ? '0' : '1'); setCollapsed(!collapsed); }}>{collapsed ? 'Mở rộng' : 'Thu gọn'}</Button></div></CardContent></Card></TabsContent>
      <TabsContent value="downloads" className="pt-4"><Card><CardHeader><CardTitle>Thư mục tải xuống</CardTitle></CardHeader><CardContent><p>{folder ? `Đã chọn: ${folder}` : 'Đang dùng thư mục tải xuống mặc định của trình duyệt.'}</p><div className="form-actions"><Button variant="outline" onClick={() => void chooseFolder()}>Chọn thư mục</Button>{folder && <Button variant="outline" onClick={() => { setDownloadDirectory(null); setFolder(null); }}>Dùng thư mục mặc định</Button>}</div><small>Áp dụng cho Excel tra cứu, báo cáo và file từ Trung tâm tải xuống trong phiên này. Trình duyệt cần hỗ trợ File System Access.</small></CardContent></Card></TabsContent>
      <TabsContent value="data" className="pt-4"><Card><CardHeader><CardTitle>Dữ liệu từ phiên bản cũ</CardTitle></CardHeader><CardContent><p>Nhập dữ liệu còn lưu trên máy vào tài khoản hiện tại. Dữ liệu đã có sẽ được kiểm tra trước khi thêm.</p><Button disabled={busy} onClick={() => void importLegacy()}>{busy ? 'Đang nhập…' : 'Nhập dữ liệu cũ'}</Button></CardContent></Card></TabsContent>
    </Tabs>
  </main>;
}
