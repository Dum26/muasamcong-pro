import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { ArrowRight, BellRing, ChartNoAxesCombined, FileSearch, LoaderCircle, ShieldCheck } from 'lucide-react';
import { authApi } from '../api/core';
import { useAuth } from '../app/AuthProvider';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import './auth.css';
import { BrandMark } from '../components/shared/BrandMark';

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true);
    try {
      if (mode === 'login') await authApi.login(email, password); else await authApi.register(email, password);
      await refresh();
      navigate(typeof location.state?.from === 'string' ? location.state.from : '/app', { replace: true });
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Không đăng nhập được.'); }
    finally { setBusy(false); }
  }

  return <main className="auth-page auth-redesign">
    <div className="auth-shell">
      <section className="auth-form-panel" aria-labelledby="auth-title">
        <Link to="/" className="auth-brand"><span className="auth-brand-mark"><BrandMark/></span><span>Bid<b>Desk</b></span></Link>
        <div className="auth-form-wrap">
          <span className="auth-kicker">BÀN LÀM VIỆC ĐẤU THẦU</span>
          <h1 id="auth-title">{mode === 'login' ? 'Chào mừng trở lại.' : 'Bắt đầu làm việc.'}</h1>
          <p className="auth-intro">{mode === 'login' ? 'Đăng nhập để tiếp tục tra cứu, theo dõi và phân tích các gói thầu của bạn.' : 'Tạo tài khoản để lưu gói quan tâm và xây dựng bàn làm việc của riêng bạn.'}</p>
          <form className="auth-form" onSubmit={submit} aria-busy={busy}>
            <div className="auth-field"><Label htmlFor="auth-email">Địa chỉ email</Label><Input id="auth-email" type="email" required maxLength={320} autoComplete="email" placeholder="ban@congty.vn" value={email} onChange={event => setEmail(event.target.value)}/></div>
            <div className="auth-field"><Label htmlFor="auth-password">Mật khẩu</Label><Input id="auth-password" type="password" required minLength={12} maxLength={128} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder="Ít nhất 12 ký tự" value={password} onChange={event => setPassword(event.target.value)}/></div>
            {error && <p role="alert" className="error">{error}</p>}
            <Button className="auth-submit" disabled={busy}>{busy ? <><LoaderCircle className="auth-spinner" size={17}/> Đang xử lý…</> : <>{mode === 'login' ? 'Đăng nhập' : 'Tạo tài khoản'} <ArrowRight size={17}/></>}</Button>
          </form>
          <p className="auth-switch">{mode === 'login' ? <>Chưa có tài khoản? <Link to="/register">Tạo tài khoản</Link></> : <>Đã có tài khoản? <Link to="/login">Đăng nhập</Link></>}</p>
        </div>
        <p className="auth-footnote"><ShieldCheck size={15}/> Dữ liệu làm việc của bạn được bảo vệ trong tài khoản riêng.</p>
      </section>

      <aside className="auth-visual-panel" aria-label="Giới thiệu BidDesk">
        <div className="auth-visual-glow" aria-hidden="true"/>
        <div className="auth-visual-content">
          <span className="auth-visual-kicker">BidDesk · Workspace</span>
          <h2>Thông tin rõ ràng.<br/><em>Quyết định tự tin.</em></h2>
          <p>Tra cứu, theo dõi và phân tích dữ liệu đấu thầu trong một luồng làm việc liền mạch.</p>
          <div className="auth-showcase" aria-hidden="true">
            <div className="auth-showcase-top"><span className="auth-showcase-logo"><ChartNoAxesCombined size={19}/></span><span>Toàn cảnh dữ liệu</span><span className="auth-showcase-dots">•••</span></div>
            <div className="auth-showcase-chart"><div className="auth-showcase-grid"/><svg viewBox="0 0 460 170" preserveAspectRatio="none"><path className="auth-chart-area" d="M0 137 C52 128 60 86 108 103 S167 143 215 88 S284 99 326 58 S391 83 460 22 L460 170 L0 170Z"/><path className="auth-chart-line" d="M0 137 C52 128 60 86 108 103 S167 143 215 88 S284 99 326 58 S391 83 460 22"/></svg></div>
            <div className="auth-showcase-bottom"><span><i/> Xu hướng gói thầu</span><span>Phân tích theo thời gian</span></div>
          </div>
          <div className="auth-float-card auth-float-left" aria-hidden="true"><span><FileSearch size={18}/></span><div><b>Tra cứu nhanh</b><small>TBMT · KHLCNT · KQLCNT</small></div></div>
          <div className="auth-float-card auth-float-right" aria-hidden="true"><span><BellRing size={18}/></span><div><b>Theo dõi thay đổi</b><small>Không bỏ lỡ cập nhật</small></div></div>
        </div>
        <span className="auth-visual-footer">Một không gian làm việc cho dữ liệu mua sắm công.</span>
      </aside>
    </div>
  </main>;
}
