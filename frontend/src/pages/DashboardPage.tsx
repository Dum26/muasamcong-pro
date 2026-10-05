import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { ArrowRight, ArrowUpRight, BellRing, BookmarkCheck, Building2, CalendarDays, ChartNoAxesCombined, Clock3, Database, Search } from 'lucide-react';
import { workspaceApi } from '../api/core';
import { dateTime, deadlineText, number } from '../lib/format';
import type { Analytics, Deadline, WatchItem } from '../types';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

export function DashboardPage() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [deadlines, setDeadlines] = useState<Deadline[]>([]);
  const [watchlist, setWatchlist] = useState<WatchItem[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    void Promise.all([workspaceApi.analytics(), workspaceApi.deadlines(), workspaceApi.watchlist()])
      .then(([stats, due, watched]) => {
        if (live) { setAnalytics(stats); setDeadlines(due.items); setWatchlist(watched.items); setError(''); }
      })
      .catch(caught => { if (live) setError(caught instanceof Error ? caught.message : 'Không lấy được dữ liệu.'); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [revision]);

  const metrics = [
    { label: 'Gói đã thu thập', value: analytics ? number(analytics.total_tenders) : '—', note: 'Trong kho dữ liệu', icon: Database },
    { label: 'Có ngày đăng', value: analytics ? number(analytics.dated_tenders) : '—', note: 'Sẵn sàng phân tích', icon: CalendarDays },
    { label: 'Đang theo dõi', value: number(watchlist.length), note: 'Gói bạn đã lưu', icon: BookmarkCheck },
    { label: 'Cập nhật mới', value: number(watchlist.filter(item => item.has_update).length), note: 'Trong danh sách theo dõi', icon: BellRing },
  ];
  const trend = analytics?.series.slice(-12) || [];
  const trendMax = Math.max(1, ...trend.map(item => item.tenders));
  const trendPoints = trend.map((item, index) => ({ ...item, x: 54 + index * 660 / Math.max(1, trend.length - 1), y: 206 - item.tenders / trendMax * 152 }));
  const trendLine = trendPoints.map(point => `${point.x},${point.y}`).join(' ');

  return <main className="page dashboard-page">
    <div className="dashboard-heading">
      <div><p className="dashboard-eyebrow">TỔNG QUAN BÀN LÀM VIỆC</p><h1>Dữ liệu đấu thầu, trong tầm nhìn.</h1><p>Theo dõi những gói quan trọng và nắm bắt xu hướng từ dữ liệu đã thu thập.</p></div>
      <Button asChild><Link to="/app/search"><Search size={16}/> Tra cứu gói thầu <ArrowUpRight size={15}/></Link></Button>
    </div>
    {error && <p role="alert" className="error">Không lấy được dữ liệu: {error} <Button variant="outline" size="sm" onClick={() => { setLoading(true); setRevision(current => current + 1); }}>Thử lại</Button></p>}
    {loading ? <div className="dashboard-metrics">{metrics.map(metric => <Skeleton key={metric.label} className="h-32 rounded-xl" />)}</div> : <div className="dashboard-metrics">{metrics.map(({ label, value, note, icon: Icon }) => <Card key={label} className="dashboard-metric"><CardContent><div className="dashboard-metric-top"><span>{label}</span><span className="dashboard-metric-icon"><Icon size={19}/></span></div><strong className="tabular-nums">{value}</strong><small>{note}</small></CardContent></Card>)}</div>}

    <div className="dashboard-feature-grid">
      <Card className="dashboard-panel dashboard-trend"><CardContent>
        <div className="dashboard-panel-heading"><div><span className="dashboard-section-label">PHÂN TÍCH DỮ LIỆU</span><h2>Xu hướng gói thầu</h2><p>Số gói có ngày đăng theo từng kỳ trong kho dữ liệu.</p></div><Link to="/app/analytics" className="dashboard-panel-link">Xem phân tích <ArrowUpRight size={15}/></Link></div>
        {trend.length ? <><div className="dashboard-chart-wrap"><svg className="dashboard-chart" viewBox="0 0 760 260" role="img" aria-label={`Xu hướng gói thầu theo thời gian, ${trend.length} kỳ`}>
          <defs><linearGradient id="dashboard-trend-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--primary)" stopOpacity=".24"/><stop offset="100%" stopColor="var(--primary)" stopOpacity="0"/></linearGradient></defs>
          {[54, 130, 206].map((y, index) => <g key={y}><line className="dashboard-grid-line" x1="54" y1={y} x2="720" y2={y}/><text className="dashboard-axis-label" x="40" y={y + 4} textAnchor="end">{number(Math.round(trendMax * (2 - index) / 2))}</text></g>)}
          {trendPoints.length > 1 && <polygon fill="url(#dashboard-trend-fill)" points={`54,206 ${trendLine} 720,206`}/>}<polyline className="dashboard-chart-line" points={trendLine}/>
          {trendPoints.map((point, index) => <g key={`${point.period}-${index}`}><circle className="dashboard-chart-dot" cx={point.x} cy={point.y} r="4"/><title>{point.period}: {number(point.tenders)} gói</title></g>)}
          {trendPoints.filter((_, index) => index % Math.max(1, Math.ceil(trendPoints.length / 6)) === 0 || index === trendPoints.length - 1).map((point, index) => <text className="dashboard-axis-label" key={`${point.period}-${index}`} x={point.x} y="242" textAnchor="middle">{point.period}</text>)}
        </svg></div><details className="dashboard-chart-details"><summary>Xem số liệu từng kỳ</summary><div>{trend.map(item => <span key={item.period}>{item.period}: <b>{number(item.tenders)}</b></span>)}</div></details></> : <div className="dashboard-empty"><ChartNoAxesCombined size={24}/><strong>Chưa có dữ liệu xu hướng</strong><span>Tra cứu và lưu gói thầu để bắt đầu xem biến động theo thời gian.</span><Link to="/app/search">Đi tới Tra cứu <ArrowRight size={14}/></Link></div>}
      </CardContent></Card>

      <Card className="dashboard-panel"><CardContent><div className="dashboard-panel-heading"><div><span className="dashboard-section-label">CẦN CHÚ Ý</span><h2>Sắp đến hạn</h2><p>Ưu tiên những gói có thời điểm đóng thầu gần nhất.</p></div><span className="dashboard-panel-icon"><Clock3 size={19}/></span></div>
        {deadlines.length ? <div className="dashboard-deadlines">{deadlines.slice(0, 5).map(item => <Link key={item.tender_code} to={`/app/tenders/${encodeURIComponent(item.tender_code)}`} className="dashboard-deadline"><span className="dashboard-deadline-title">{item.title || item.tender_code}</span><span className="dashboard-deadline-meta">{item.tender_code} · {item.investor_name || 'Chưa có chủ đầu tư'}</span><span className="dashboard-deadline-bottom"><strong className={item.remaining_seconds !== null && item.remaining_seconds < 86400 ? 'urgent' : ''}>{deadlineText(item.remaining_seconds)}</strong><small>{dateTime(item.bid_closing_date)}</small></span></Link>)}</div> : <div className="dashboard-empty dashboard-empty-compact"><Clock3 size={24}/><strong>Chưa có gói sắp đến hạn</strong><span>Gói có thời điểm đóng thầu sẽ xuất hiện tại đây.</span></div>}
      </CardContent></Card>
    </div>

    <div className="dashboard-secondary-grid">
      <Card className="dashboard-panel"><CardContent><div className="dashboard-panel-heading"><div><span className="dashboard-section-label">CƠ CẤU DỮ LIỆU</span><h2>Chủ đầu tư nổi bật</h2><p>Những chủ đầu tư có nhiều gói nhất trong dữ liệu.</p></div><span className="dashboard-panel-icon"><Building2 size={19}/></span></div>
        {analytics?.top_investors?.length ? <div className="dashboard-investors">{analytics.top_investors.slice(0, 6).map((item, index) => <div className="dashboard-investor" key={`${item.investor_name}-${index}`}><span className="dashboard-investor-name" title={item.investor_name || 'Chưa rõ'}>{item.investor_name || 'Chưa rõ'}</span><div className="dashboard-bar-track"><span style={{ width: `${Math.max(3, item.count / Math.max(1, analytics.top_investors[0].count) * 100)}%` }}/></div><strong className="tabular-nums">{number(item.count)}</strong></div>)}</div> : <div className="dashboard-empty dashboard-empty-compact"><Building2 size={24}/><strong>Chưa có dữ liệu chủ đầu tư</strong><span>Thông tin sẽ xuất hiện sau khi thu thập gói thầu.</span></div>}
      </CardContent></Card>

      <Card className="dashboard-panel"><CardContent><div className="dashboard-panel-heading"><div><span className="dashboard-section-label">CÔNG VIỆC CỦA BẠN</span><h2>Gói đang theo dõi</h2><p>Truy cập nhanh và xem các cập nhật gần đây.</p></div><Link to="/app/watchlist" className="dashboard-panel-link">Xem tất cả <ArrowUpRight size={15}/></Link></div>
        {watchlist.length ? <div className="dashboard-watchlist">{watchlist.slice(0, 5).map(item => <Link key={item.code} to={`/app/tenders/${encodeURIComponent(item.code)}`} className="dashboard-watch-item"><span className="dashboard-watch-icon"><BookmarkCheck size={17}/></span><span className="dashboard-watch-text"><strong>{item.name || item.code}</strong><small>{item.code} · {item.investor || 'Chưa có chủ đầu tư'}</small></span>{item.has_update ? <span className="dashboard-update">Mới</span> : <ArrowUpRight className="dashboard-watch-arrow" size={15}/>}</Link>)}</div> : <div className="dashboard-empty dashboard-empty-compact"><BookmarkCheck size={24}/><strong>Chưa theo dõi gói nào</strong><span>Lưu gói bạn quan tâm để quản lý tại đây.</span><Link to="/app/search">Tìm gói thầu <ArrowRight size={14}/></Link></div>}
      </CardContent></Card>
    </div>
  </main>;
}
