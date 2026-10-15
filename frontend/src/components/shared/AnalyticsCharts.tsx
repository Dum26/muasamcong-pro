import { useId } from 'react';
import { number } from '../../lib/format';

interface Trend { period: string; tenders: number; results: number }
interface Dimension { value: string; count: number }

export function AnalyticsTrend({ items, onSelect }: { items: Trend[]; onSelect: (period: string) => void }) {
  const gradient = useId();
  const chart = items.slice(-24);
  const max = Math.max(1, ...chart.flatMap(item => [item.tenders, item.results]));
  const x = (index: number) => 56 + index * 660 / Math.max(1, chart.length - 1);
  const y = (value: number) => 230 - value * 180 / max;
  const points = (field: 'tenders' | 'results') => chart.map((item, index) => `${x(index)},${y(item[field])}`).join(' ');
  if (!chart.length) return <div className="analytics-empty">Chưa có dữ liệu theo thời gian trong phạm vi này.</div>;
  return <>
    <div className="analytics-legend"><span><i/>Thông báo mời thầu</span><span><i className="result"/>Có KQLCNT</span></div>
    <div className="analytics-chart-scroll"><svg viewBox="0 0 760 280" className="analytics-trend" role="group" aria-label="Xu hướng thông báo mời thầu và kết quả lựa chọn nhà thầu">
      <defs><linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop stopColor="var(--analytics-blue)" stopOpacity=".22"/><stop offset="1" stopColor="var(--analytics-blue)" stopOpacity=".01"/></linearGradient></defs>
      {[0, 1, 2, 3, 4].map(tick => <g key={tick}><line x1="56" x2="716" y1={y(max * tick / 4)} y2={y(max * tick / 4)} className="analytics-grid"/><text x="44" y={y(max * tick / 4) + 4} textAnchor="end" className="analytics-axis">{number(Math.ceil(max * tick / 4))}</text></g>)}
      <polygon points={`56,230 ${points('tenders')} ${x(chart.length - 1)},230`} fill={`url(#${gradient})`}/>
      <polyline points={points('results')} className="analytics-result-line"/>
      <polyline points={points('tenders')} className="analytics-tender-line"/>
      {chart.map((item, index) => <g key={item.period} role="button" tabIndex={0} className="analytics-point" aria-label={`${item.period}: ${number(item.tenders)} TBMT, ${number(item.results)} có KQLCNT. Bấm để xem dữ liệu.`} onClick={() => onSelect(item.period)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(item.period); } }}>
        <title>{`${item.period}: ${number(item.tenders)} TBMT · ${number(item.results)} có KQLCNT`}</title>
        <circle cx={x(index)} cy={y(item.tenders)} r="13" fill="transparent"/>
        <circle cx={x(index)} cy={y(item.tenders)} r="4" className="analytics-dot"/>
        {(index % Math.max(1, Math.ceil(chart.length / 6)) === 0 || index === chart.length - 1) && <text x={x(index)} y="260" textAnchor="middle" className="analytics-axis">{item.period}</text>}
      </g>)}
    </svg></div>
    <p className="analytics-hint">Bấm vào điểm trên biểu đồ để xem các gói trong kỳ.</p>
    <details className="analytics-data"><summary>Xem đầy đủ số liệu</summary><table><thead><tr><th>Thời gian</th><th>TBMT</th><th>Có KQLCNT</th></tr></thead><tbody>{chart.map(item => <tr key={item.period}><td>{item.period}</td><td>{number(item.tenders)}</td><td>{number(item.results)}</td></tr>)}</tbody></table></details>
  </>;
}

export function AnalyticsBars({ items, label, onSelect }: { items: Dimension[]; label: string; onSelect: (value: string) => void }) {
  const chart = items.slice(0, 10);
  const max = Math.max(1, ...chart.map(item => item.count));
  if (!chart.length) return <div className="analytics-empty">Chưa có dữ liệu {label.toLocaleLowerCase('vi')} trong phạm vi này.</div>;
  return <>
    <div className="analytics-bars-scroll"><div className="analytics-bars" style={{ minWidth: `${Math.max(300, chart.length * 76)}px` }}>
      <div className="analytics-bar-grid" aria-hidden="true">{[0, 1, 2, 3].map(tick => <span key={tick}/>)}</div>
      {chart.map((item, index) => <button type="button" className="analytics-bar" key={item.value} onClick={() => onSelect(item.value)} aria-label={`${item.value}: ${number(item.count)} gói. Bấm để xem dữ liệu.`} title={`${item.value}: ${number(item.count)} gói`}>
        <span className="analytics-bar-column"><span className={`analytics-bar-fill tone-${index % 3}`} style={{ height: `${item.count / max * 100}%` }}><b>{number(item.count)}</b></span></span>
        <span className="analytics-bar-label">{item.value}</span>
      </button>)}
    </div></div>
    <p className="analytics-hint">{chart.length} nhóm · Bấm cột để xem gói liên quan.</p>
    <details className="analytics-data"><summary>Xem tên đầy đủ và số liệu</summary><table><thead><tr><th>{label}</th><th>Số gói</th></tr></thead><tbody>{items.map(item => <tr key={item.value}><td><button type="button" onClick={() => onSelect(item.value)}>{item.value}</button></td><td>{number(item.count)}</td></tr>)}</tbody></table></details>
  </>;
}
