import { Component, lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router';
import { Activity, Bell, BookOpen, ChartNoAxesCombined, Clock3, Download, FileText, LayoutDashboard, ListFilter, LogOut, Menu, Moon, Search, Settings, ShieldCheck, Star, Sun, Workflow } from 'lucide-react';
import { useAuth } from './AuthProvider';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Toaster } from '@/components/ui/sonner';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
const CommandPalette = lazy(() => import('./CommandPalette').then(module => ({ default: module.CommandPalette })));
const AuthPage = lazy(() => import('../pages/AuthPage').then(page => ({ default: page.AuthPage })));
const DashboardPage = lazy(() => import('../pages/DashboardPage').then(page => ({ default: page.DashboardPage })));
const SearchPage = lazy(() => import('../pages/SearchPage').then(page => ({ default: page.SearchPage })));
const TenderPage = lazy(() => import('../pages/TenderPage').then(page => ({ default: page.TenderPage })));
const WatchlistPage = lazy(() => import('../pages/WatchlistPage').then(page => ({ default: page.WatchlistPage })));
const HistoryPage = lazy(() => import('../pages/HistoryPage').then(page => ({ default: page.HistoryPage })));
const NotificationsPage = lazy(() => import('../pages/NotificationsPage').then(page => ({ default: page.NotificationsPage })));
const DownloadsPage = lazy(() => import('../pages/DownloadsPage').then(page => ({ default: page.DownloadsPage })));
const DocumentsPage = lazy(() => import('../pages/DocumentsPage').then(page => ({ default: page.DocumentsPage })));
const AutomationPage = lazy(() => import('../pages/AutomationPage').then(page => ({ default: page.AutomationPage })));
const AnalyticsPage = lazy(() => import('../pages/AnalyticsPage').then(page => ({ default: page.AnalyticsPage })));
const SettingsPage = lazy(() => import('../pages/SettingsPage').then(page => ({ default: page.SettingsPage })));
const AiPage = lazy(() => import('../pages/AiPage').then(page => ({ default: page.AiPage })));
const AdminPage = lazy(() => import('../pages/AdminPage').then(page => ({ default: page.AdminPage })));
const CodesPage = lazy(() => import('../pages/CodesPage').then(page => ({ default: page.CodesPage })));
const ReportBuilderPage = lazy(() => import('../pages/ReportBuilderPage').then(page => ({ default: page.ReportBuilderPage })));
const ArchiveSearchPage = lazy(() => import('../pages/ArchiveSearchPage').then(page => ({ default: page.ArchiveSearchPage })));
const ComparePage = lazy(() => import('../pages/ComparePage').then(page => ({ default: page.ComparePage })));
const EntityPage = lazy(() => import('../pages/EntityPage').then(page => ({ default: page.EntityPage })));

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) { console.error('React view failed', error); }
  render() { return this.state.failed ? <main className="center-state"><h1>Không hiển thị được khu vực này</h1><p>Hãy tải lại trang hoặc quay về Tổng quan.</p><a href="/app">Về Tổng quan</a></main> : this.props.children; }
}

function Protected({ admin = false }: { admin?: boolean }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="center-state">Đang kiểm tra phiên đăng nhập…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (admin && user.role !== 'admin') return <div className="center-state"><h1>Không có quyền truy cập</h1><Link to="/app">Về Tổng quan</Link></div>;
  return <Outlet />;
}

const navGroups = [
  { label: 'Công việc', items: [
    { to: '/app', label: 'Tổng quan', icon: LayoutDashboard },
    { to: '/app/search', label: 'Tra cứu', icon: Search },
    { to: '/app/archive', label: 'Kho dữ liệu', icon: BookOpen },
    { to: '/app/watchlist', label: 'Theo dõi', icon: Star },
    { to: '/app/documents', label: 'Tài liệu', icon: FileText },
    { to: '/app/automations', label: 'Tự động hóa', icon: Workflow },
    { to: '/app/analytics', label: 'Phân tích', icon: ChartNoAxesCombined },
    { to: '/app/ai', label: 'AI Hồ sơ', icon: BookOpen },
  ] },
  { label: 'Công cụ', items: [
    { to: '/app/codes', label: 'Danh sách mã', icon: ListFilter },
    { to: '/app/history', label: 'Lịch sử', icon: Clock3 },
    { to: '/app/notifications', label: 'Thông báo', icon: Bell },
    { to: '/app/downloads', label: 'Tải xuống', icon: Download },
  ] },
  { label: 'Hệ thống', items: [{ to: '/app/settings', label: 'Cài đặt', icon: Settings }] },
];
const nav = navGroups.flatMap(group => group.items);

function Shell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(localStorage.getItem('msc_react_sidebar') === '1');
  const [dark, setDark] = useState(localStorage.getItem('msc_theme') !== 'light');
  const [palette, setPalette] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; document.documentElement.classList.toggle('dark', dark); localStorage.setItem('msc_theme', dark ? 'dark' : 'light'); }, [dark]);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setPalette(true); }
    };
    document.addEventListener('keydown', shortcut);
    return () => document.removeEventListener('keydown', shortcut);
  }, []);
  const title = nav.find(item => item.to === location.pathname)?.label || (location.pathname.startsWith('/app/admin') ? 'Quản trị' : location.pathname.includes('/tenders/') ? 'Chi tiết gói thầu' : 'Bàn làm việc');
  const navLink = ({ to, label, icon: Icon }: (typeof nav)[number]) => {
    const active = to === '/app' ? location.pathname === to : location.pathname.startsWith(to);
    return <Tooltip key={to}><TooltipTrigger asChild><Link to={to} onClick={() => setMobileOpen(false)} aria-current={active ? 'page' : undefined} className={active ? 'active' : ''}><Icon size={18}/><span>{label}</span></Link></TooltipTrigger><TooltipContent side="right">{label}</TooltipContent></Tooltip>;
  };
  const navLinks = navGroups.map(group => <div className="nav-group" key={group.label}><small>{group.label}</small>{group.items.map(navLink)}</div>);
  return <TooltipProvider><a className="skip-link" href="#main-content">Chuyển tới nội dung</a><div className={`app-shell ${collapsed ? 'collapsed' : ''}`}>
    <aside className="sidebar"><div className="brand"><span className="brand-icon">M</span><span>MuaSamCong <b>Pro</b></span></div>
      <nav aria-label="Điều hướng chính">{navLinks}
        {user?.role === 'admin' && <div className="nav-group"><small>Quản trị</small><Tooltip><TooltipTrigger asChild><Link to="/app/admin" aria-current={location.pathname.startsWith('/app/admin') ? 'page' : undefined} className={location.pathname.startsWith('/app/admin') ? 'active' : ''}><ShieldCheck size={18}/><span>Quản trị</span></Link></TooltipTrigger><TooltipContent side="right">Quản trị</TooltipContent></Tooltip></div>}
      </nav><Button variant="ghost" className="sidebar-toggle" onClick={() => { localStorage.setItem('msc_react_sidebar', collapsed ? '0' : '1'); setCollapsed(!collapsed); }}><Menu size={18}/><span>{collapsed ? 'Mở rộng' : 'Thu gọn'}</span></Button>
    </aside>
    <div className="main-wrap"><header className="topbar"><div className="flex min-w-0 items-center gap-2"><Button className="mobile-nav-trigger" variant="ghost" size="icon" aria-label="Mở điều hướng" onClick={() => setMobileOpen(true)}><Menu size={18}/></Button><span className="muted">Bàn làm việc / </span><strong className="truncate">{title}</strong></div><div className="top-actions"><Button variant="outline" onClick={() => setPalette(true)} className="global-search"><Search size={16}/> Tìm kiếm nhanh <kbd>Ctrl K</kbd></Button><Button asChild variant="ghost" size="icon" aria-label="Mở thông báo"><Link to="/app/notifications"><Bell size={18}/></Link></Button><Button variant="ghost" size="icon" aria-label="Đổi giao diện" onClick={() => setDark(!dark)}>{dark ? <Sun size={18}/> : <Moon size={18}/>}</Button><span className="user-chip">{user?.email}</span><Button variant="ghost" size="icon" aria-label="Đăng xuất" title="Đăng xuất" onClick={() => void logout().then(() => navigate('/login'))}><LogOut size={18}/></Button></div></header><div id="main-content" tabIndex={-1}><ErrorBoundary key={location.pathname}><Outlet context={{ dark, setDark, collapsed, setCollapsed }} /></ErrorBoundary></div></div>
    <Sheet open={mobileOpen} onOpenChange={setMobileOpen}><SheetContent side="left" className="w-72"><SheetHeader><SheetTitle>MuaSamCong Pro</SheetTitle><SheetDescription>Điều hướng bàn làm việc</SheetDescription></SheetHeader><nav className="sheet-nav" aria-label="Điều hướng trên điện thoại">{navLinks}{user?.role === 'admin' && <Link to="/app/admin" onClick={() => setMobileOpen(false)}><ShieldCheck size={18}/> Quản trị</Link>}</nav></SheetContent></Sheet>
    <Suspense fallback={null}>{palette && <CommandPalette nav={nav} onClose={() => setPalette(false)} />}</Suspense>
    <Toaster theme={dark ? 'dark' : 'light'} position="bottom-right" richColors/>
  </div></TooltipProvider>;
}

export function App() { return <Suspense fallback={<div className="center-state">Đang tải trang…</div>}><Routes>
  <Route path="/login" element={<AuthPage mode="login"/>}/><Route path="/register" element={<AuthPage mode="register"/>}/>
  <Route element={<Protected/>}><Route element={<Shell/>}>
    <Route path="/app" element={<DashboardPage/>}/><Route path="/app/search" element={<SearchPage/>}/>
    <Route path="/app/archive" element={<ArchiveSearchPage/>}/>
    <Route path="/app/compare" element={<ComparePage/>}/>
    <Route path="/app/entities/:kind/:id" element={<EntityPage/>}/>
    <Route path="/app/codes" element={<CodesPage/>}/>
    <Route path="/app/tenders/:code" element={<TenderPage/>}/><Route path="/app/watchlist" element={<WatchlistPage/>}/>
    <Route path="/app/plans/:code" element={<TenderPage/>}/>
    <Route path="/app/history" element={<HistoryPage/>}/><Route path="/app/notifications" element={<NotificationsPage/>}/>
    <Route path="/app/documents" element={<DocumentsPage/>}/><Route path="/app/documents/:source/:id" element={<DocumentsPage/>}/>
    <Route path="/app/automations" element={<AutomationPage/>}/>
    <Route path="/app/analytics" element={<AnalyticsPage/>}/>
    <Route path="/app/reports" element={<ReportBuilderPage/>}/>
    <Route path="/app/ai" element={<AiPage/>}/>
    <Route path="/app/admin" element={<Protected admin/>}><Route index element={<AdminPage/>}/></Route>
    <Route path="/app/settings" element={<SettingsPage/>}/>
    <Route path="/app/downloads" element={<DownloadsPage/>}/>
  </Route></Route>
  <Route path="/admin/*" element={<Protected admin/>}><Route path="*" element={<Navigate to="/app/admin" replace/>}/></Route>
  <Route path="*" element={<main className="center-state"><Activity size={32}/><h1>Không tìm thấy trang</h1><Link to="/app">Về bàn làm việc</Link></main>}/>
</Routes></Suspense>; }
