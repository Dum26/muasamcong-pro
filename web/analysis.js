// Monthly overview uses search results, independently of Excel lot downloads.
function reportMonth(row) {
  const value=String(row.public_date||'');
  if(!parseViDate(value))return '';
  const [, ,month,year]=value.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  return `${year}-${month.padStart(2,'0')}`;
}
function reportGroup(row) {
  const name=normalizeSearch(row.package_name||row.plan_name||'');
  if(/\bgeneric\b/.test(name))return 'Thuốc generic';
  if(name.includes('biet duoc'))return 'Biệt dược';
  if(name.includes('duoc lieu')||name.includes('co truyen'))return 'Dược liệu / cổ truyền';
  if(name.includes('thiet bi'))return 'Thiết bị';
  if(name.includes('vat tu'))return 'Vật tư';
  if(name.includes('thuoc'))return 'Thuốc khác';
  return 'Khác / chưa phân loại';
}
function reportWinnerNames(row) {
  return String(row.winner||'').split(';').map(name=>name.trim()).filter(name=>name&&!['—','-'].includes(name));
}
function reportInvestorNames(row) {
  const name=String(row.investor_name||'').trim();
  return name&&!['—','-','Chưa có chủ đầu tư'].includes(name)?[name]:[];
}
function reportCounts(rows, labels) {
  const counts=new Map();
  for(const row of rows) {
    const unique=new Map();
    for(const raw of labels(row)) {
      const label=String(raw||'').trim().replace(/\s+/g,' ');
      if(label)unique.set(label.toLocaleLowerCase('vi'),label);
    }
    for(const [key,label] of unique) {
      const item=counts.get(key)||{label,count:0}; item.count++; counts.set(key,item);
    }
  }
  return [...counts.values()].sort((a,b)=>b.count-a.count||a.label.localeCompare(b.label,'vi'));
}
function monthlyReport(rows, month='', keyword='') {
  const terms=normalizeSearch(keyword).trim().split(/\s+/).filter(Boolean);
  const named=rows.filter(row=>terms.every(term=>normalizeSearch(row.package_name||row.plan_name||'').includes(term)));
  const scoped=named.filter(row=>!month||reportMonth(row)===month);
  return {rows:scoped, unknownDates:named.filter(row=>!reportMonth(row)).length,
    trend:reportCounts(named,row=>[reportMonth(row)]).sort((a,b)=>a.label.localeCompare(b.label)),
    locations:reportCounts(scoped,row=>[row.location||'Chưa có địa điểm']),
    groups:reportCounts(scoped,row=>[reportGroup(row)]),
    winners:reportCounts(scoped,reportWinnerNames), knownWinners:scoped.filter(row=>reportWinnerNames(row).length).length,
    investors:reportCounts(scoped,reportInvestorNames), knownInvestors:scoped.filter(row=>reportInvestorNames(row).length).length,
    statuses:reportCounts(scoped,row=>[row.tender_status||'Chưa xác định']),
    forms:reportCounts(scoped,row=>[row.bid_form||'Chưa có hình thức'])};
}
function reportBars(id, items, denominator, limit=10, measure='count') {
  const shown=items.slice(0,limit), percent=measure==='percent';
  const value=item=>percent?(denominator?item.count/denominator*100:0):item.count;
  const step=Math.max(1,Math.ceil(Math.max(0,...shown.map(value))/4)), max=step*4;
  if(!shown.length){$(id).innerHTML='<p class="chart-empty">Chưa có dữ liệu trong phạm vi này.</p>';return;}
  const bottom=shown.length*48+35, height=bottom+65;
  let svg=`<svg class="xy-chart" viewBox="0 0 700 ${height}" role="img" aria-label="Phân bố theo nhóm, ${percent?'tỷ lệ phần trăm':'số kết quả'}"><title>Phân bố theo nhóm</title>`;
  for(let i=0;i<=4;i++){const x=215+i*105;svg+=`<line class="xy-grid" x1="${x}" y1="15" x2="${x}" y2="${bottom}"/><text class="xy-tick" x="${x}" y="${bottom+23}" text-anchor="middle">${i*step}${percent?'%':''}</text>`;}
  svg+=`<path class="xy-axis" d="M215 15 V${bottom} H645"/><text class="xy-axis-label" x="425" y="${bottom+51}" text-anchor="middle">${percent?'Tỷ lệ (%)':'Số kết quả'}</text><text class="xy-axis-label" x="12" y="15">Nhóm</text>`;
  shown.forEach((item,index)=>{const y=32+index*48, width=value(item)/max*420, short=item.label.length>28?item.label.slice(0,27)+'…':item.label;
    const pct=denominator?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(item.count/denominator*100):'0';
    svg+=`<g class="xy-item" data-chart-id="${id}" data-chart-index="${index}" tabindex="0" role="button" aria-label="Xem ${item.count} mã của ${esc(item.label)}"><title>${esc(item.label)}: ${item.count} kết quả (${pct}%) · bấm để xem mã</title><text class="xy-category" x="200" y="${y+19}" text-anchor="end">${esc(short)}</text><rect x="215" y="${y}" width="${width}" height="29" rx="5"/><text class="xy-value" x="${223+width}" y="${y+20}">${percent?pct+'%':item.count}</text></g>`;
  });
  $(id).innerHTML=`<div class="xy-scroll">${svg}</svg></div><details class="chart-data"><summary>Xem tên đầy đủ và số liệu</summary><table><thead><tr><th>Nhóm</th><th>Kết quả</th><th>Tỷ lệ</th></tr></thead><tbody>${shown.map(item=>`<tr><td>${esc(item.label)}</td><td>${item.count}</td><td>${denominator?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(item.count/denominator*100):0}%</td></tr>`).join('')}</tbody></table></details>`;
}
function reportColumns(id, items, denominator) {
  const shown=items.slice(0,10);
  if(!shown.length){$(id).innerHTML='<p class="chart-empty">Chưa có dữ liệu trong phạm vi này.</p>';return;}
  const names={reportLocations:'Địa điểm',reportInvestorChart:'Chủ đầu tư',reportStatuses:'Trạng thái đấu thầu',reportForms:'Hình thức LCNT'};
  const category=names[id]||'Nhóm';
  const left=62, top=39, bottom=278;
  const minimumWidth=id==='reportInvestorChart'?280:id==='reportLocations'?540:440;
  const width=Math.max(minimumWidth,left+shown.length*76+28);
  const stepX=(width-18-left)/shown.length;
  const highest=Math.max(...shown.map(item=>item.count)), tickStep=Math.max(1,Math.ceil(highest/4)), ceiling=tickStep*4;
  const x=index=>left+stepX*(index+.5);
  const y=count=>bottom-count/ceiling*(bottom-top);
  let svg=`<svg class="xy-chart xy-column-chart" viewBox="0 0 ${width} 440" style="min-width:${width}px" role="img" aria-label="${category} theo số kết quả"><title>${category} theo số kết quả</title>`;
  for(let tick=0;tick<=4;tick++){const yy=y(tick*tickStep);svg+=`<line class="xy-grid" x1="${left}" y1="${yy}" x2="${width-18}" y2="${yy}"/><text class="xy-tick" x="${left-11}" y="${yy+5}" text-anchor="end">${tick*tickStep}</text>`;}
  svg+=`<path class="xy-axis" d="M${left} ${top} V${bottom} H${width-18}"/><text class="xy-axis-label" x="13" y="164" transform="rotate(-90 13 164)" text-anchor="middle">Số kết quả</text><text class="xy-axis-label" x="${width/2}" y="431" text-anchor="middle">${category}</text>`;
  shown.forEach((item,index)=>{
    const center=x(index), barTop=y(item.count);
    const display=id==='reportLocations'?item.label.replace(/^(Thành phố|Tỉnh)\s+/i,'').replace(/^Hồ Chí Minh$/i,'TP.HCM'):item.label;
    const label=display.length>22?display.slice(0,21)+'…':display;
    const pct=denominator?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(item.count/denominator*100):'0';
    svg+=`<g class="xy-item" data-chart-id="${id}" data-chart-index="${index}" tabindex="0" role="button" aria-label="Xem ${item.count} mã thuộc ${esc(item.label)}"><title>${esc(item.label)}: ${item.count} kết quả (${pct}%) · bấm để xem mã</title><rect x="${center-25}" y="${barTop}" width="50" height="${bottom-barTop}" rx="5"/><text class="xy-value" x="${center}" y="${barTop-9}" text-anchor="middle">${item.count}</text><text class="xy-category" x="${center}" y="${bottom+30}" text-anchor="end" transform="rotate(-45 ${center} ${bottom+30})">${esc(label)}</text></g>`;
  });
  $(id).innerHTML=`<div class="xy-scroll">${svg}</svg></div><details class="chart-data"><summary>Xem tên đầy đủ và số liệu</summary><table><thead><tr><th>${category}</th><th>Kết quả</th><th>Tỷ lệ</th></tr></thead><tbody>${shown.map(item=>`<tr><td>${esc(item.label)}</td><td>${item.count}</td><td>${denominator?new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(item.count/denominator*100):0}%</td></tr>`).join('')}</tbody></table></details>`;
}
function reportDonut(id, items, denominator) {
  if(!items.length){$(id).innerHTML='<p class="chart-empty">Chưa có dữ liệu trong phạm vi này.</p>';return;}
  const colors=['#35d5df','#6b6cf1','#d65bdd','#36a9fa','#e6a85b','#7bd1a0'];
  const radius=57, circumference=2*Math.PI*radius;
  let offset=0;
  const segments=items.map((item,index)=>{
    const length=denominator?item.count/denominator*circumference:0;
    const markup=`<circle class="xy-item donut-segment" data-chart-id="${id}" data-chart-index="${index}" tabindex="0" role="button" aria-label="Xem ${item.count} mã của ${esc(item.label)}" cx="80" cy="80" r="${radius}" fill="none" stroke="${colors[index%colors.length]}" stroke-width="22" stroke-dasharray="${length} ${circumference-length}" stroke-dashoffset="${-offset}" transform="rotate(-90 80 80)"><title>${esc(item.label)}: ${item.count} kết quả · bấm để xem mã</title></circle>`;
    offset+=length;
    return markup;
  }).join('');
  $(id).innerHTML=`<div class="donut-layout"><svg class="donut-chart" viewBox="0 0 160 160" role="img" aria-label="Tỷ trọng nhóm mặt hàng"><circle cx="80" cy="80" r="${radius}" fill="none" stroke="var(--dashboard-track)" stroke-width="22"/>${segments}<text x="80" y="76" text-anchor="middle" class="donut-total">${denominator}</text><text x="80" y="96" text-anchor="middle" class="donut-caption">kết quả</text></svg><div class="donut-legend">${items.map((item,index)=>`<button type="button" class="donut-legend-item" data-chart-id="${id}" data-chart-index="${index}"><i style="background:${colors[index%colors.length]}"></i><span title="${esc(item.label)}">${esc(item.label)}</span><strong>${item.count}</strong></button>`).join('')}</div></div><p class="dashboard-chart-help">Chọn một nhóm để xem các mã liên quan.</p>`;
}
function reportDailyTrend(rows,month) {
  if(!month)return [];
  const counts=new Map();
  for(const row of rows)if(reportMonth(row)===month){const day=String(Number(String(row.public_date).match(/^\d{1,2}/)[0])).padStart(2,'0');counts.set(day,(counts.get(day)||0)+1);}
  if(!counts.size)return [];
  const first=Math.min(...[...counts.keys()].map(Number)),last=Math.max(...[...counts.keys()].map(Number));
  return Array.from({length:last-first+1},(_,index)=>{const day=String(first+index).padStart(2,'0');return {label:`${month}-${day}`,count:counts.get(day)||0};});
}
function reportLabels(row,dimension) {
  if(dimension==='groups')return [reportGroup(row)];
  if(dimension==='locations')return [row.location||'Chưa có địa điểm'];
  if(dimension==='winners')return reportWinnerNames(row);
  if(dimension==='investors')return reportInvestorNames(row);
  if(dimension==='statuses')return [row.tender_status||'Chưa xác định'];
  if(dimension==='forms')return [row.bid_form||'Chưa có hình thức'];
  return ['Tổng kết quả'];
}
function reportChartLabels(row,id) {
  if(id==='reportLocations')return [row.location||'Chưa có địa điểm'];
  if(id==='reportInvestorChart')return reportInvestorNames(row);
  if(id==='reportStatuses')return [row.tender_status||'Chưa xác định'];
  if(id==='reportForms')return [row.bid_form||'Chưa có hình thức'];
  return [];
}
function reportCode(row) { return row.notify_no||planDisplayCode(row)||row.package_no||''; }
function showChartCodes(label,rows) {
  state.reportSelectedRows=rows;
  const codes=[...new Set(rows.map(reportCode).filter(Boolean))];
  $('chartSelectionTitle').textContent=`${label} · ${rows.length} kết quả · ${codes.length} mã`;
  $('chartSelectionHint').textContent='Bấm mã để xem chi tiết, hoặc chọn “Xem trong bảng” để tới đúng dòng.';
  $('copyChartCodes').disabled=!codes.length;
  $('chartSelectionList').innerHTML=rows.length?rows.map(row=>{
    const index=Number.isInteger(row.index)?row.index:state.rows.indexOf(row);
    const code=reportCode(row);
    const name=esc(row.package_name||row.plan_name||'—'),url=officialDetailUrl(row);
    const packageCell=url?`<a class="chart-package-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer" title="Mở trên e-GP: ${name}">${name} ↗</a>`:`<span title="${name}">${name}</span>`;
    return `<div class="chart-code-row"><button type="button" class="chart-code-link" data-chart-detail="${index}">${esc(code)}</button>${packageCell}<small>${esc(row.location||row.public_date||'')}</small><button type="button" class="chart-table-link" data-chart-table="${index}">Xem trong bảng ↗</button></div>`;
  }).join(''):'<p class="chart-empty">Điểm này chưa có mã nào trong phạm vi đang xem.</p>';
  $('chartSelection').classList.remove('hidden');
  $('chartSelection').scrollIntoView?.({behavior:'smooth',block:'start'});
}
function showBarCodes(target) {
  const id=target.dataset.chartId, index=Number(target.dataset.chartIndex);
  const item=state.reportChartItems?.[id]?.[index];
  if(!item)return;
  const key=item.label.toLocaleLowerCase('vi');
  const rows=(state.reportDashboardRows||[]).filter(row=>reportChartLabels(row,id).some(value=>String(value).trim().toLocaleLowerCase('vi')===key));
  showChartCodes(item.label,rows);
}
function showTrendCodes(target) {
  const period=target.dataset.chartPeriod, dimension=target.dataset.chartDimension, label=target.dataset.chartSeries;
  const periodRows=(state.reportTimelineRows||[]).filter(row=>{
    const month=reportMonth(row);
    if(!month)return false;
    if(period.length===7)return month===period;
    const day=String(Number(String(row.public_date).match(/^\d{1,2}/)?.[0]||0)).padStart(2,'0');
    return `${month}-${day}`===period;
  });
  const key=label.toLocaleLowerCase('vi');
  const rows=dimension==='total'?periodRows:periodRows.filter(row=>reportLabels(row,dimension).some(value=>value.toLocaleLowerCase('vi')===key));
  showChartCodes(`${label} · ${period}`,rows);
}
function reportTimelineChart(rows, selectedMonth, dimension, limit, measure, hidden=new Set()) {
  const dated=rows.filter(row=>reportMonth(row));
  const months=[...new Set(dated.map(reportMonth))].sort();
  const daily=Boolean(selectedMonth)||(months.length===1);
  const month=selectedMonth||months[0]||'';
  const scoped=dated.filter(row=>!selectedMonth||reportMonth(row)===selectedMonth);
  const periods=daily?reportDailyTrend(scoped,month).map(item=>item.label):months;
  if(!periods.length||!scoped.length)return {html:'<p class="chart-empty">Chưa có ngày đăng tải hợp lệ trong phạm vi này.</p>',seriesCount:0,daily};
  const groups=dimension==='total'?[{label:'Tổng kết quả',count:scoped.length}]:reportCounts(scoped,row=>reportLabels(row,dimension)).slice(0,limit);
  const colors=['#5577d5','#e2905a','#42a99a','#ab7ac4','#d4ad47','#5d9fc3','#cc7189','#7c9c63','#a585cd','#638eaa'];
  const byPeriod=new Map(periods.map(period=>[period,[]]));
  for(const row of scoped){const period=daily?`${reportMonth(row)}-${String(Number(String(row.public_date).match(/^\d{1,2}/)[0])).padStart(2,'0')}`:reportMonth(row);byPeriod.get(period)?.push(row);}
  const series=groups.map((group,index)=>({label:group.label,color:colors[index%colors.length],values:periods.map(period=>{
    const periodRows=byPeriod.get(period)||[];
    const count=dimension==='total'?periodRows.length:periodRows.filter(row=>reportLabels(row,dimension).some(label=>label.toLocaleLowerCase('vi')===group.label.toLocaleLowerCase('vi'))).length;
    return measure==='percent'?(dimension==='total'?count/scoped.length*100:(periodRows.length?count/periodRows.length*100:0)):count;
  })}));
  const width=Math.max(900,periods.length*(daily?30:78)+100), legendRows=Math.ceil(series.length/3), height=355+legendRows*30;
  const left=72,right=width-35,top=35,bottom=270,span=right-left;
  const highest=Math.max(0,...series.flatMap(item=>item.values));
  const step=Math.max(1,Math.ceil(highest/5)),ceiling=step*5;
  const x=index=>periods.length===1?left+span/2:left+span*index/(periods.length-1);
  const y=value=>bottom-(value/ceiling)*(bottom-top);
  const unit=measure==='percent'?'%':'';
  let svg=`<svg class="xy-chart report-line-chart" viewBox="0 0 ${width} ${height}" style="min-width:${width}px" role="img" aria-label="Biểu đồ đường theo ${daily?'ngày':'tháng'} đăng tải"><title>Diễn biến đấu thầu theo ${daily?'ngày':'tháng'} đăng tải</title>`;
  for(let tick=0;tick<=5;tick++){const yy=y(tick*step);svg+=`<line class="xy-grid" x1="${left}" y1="${yy}" x2="${right}" y2="${yy}"/><text class="xy-tick" x="${left-12}" y="${yy+5}" text-anchor="end">${tick*step}${unit}</text>`;}
  svg+=`<path class="xy-axis" d="M${left} ${top} V${bottom} H${right}"/>`;
  periods.forEach((period,index)=>{if(!daily||index===0||index===periods.length-1||index%5===4){const label=daily?period.slice(8):period.slice(5)+'/'+period.slice(0,4);svg+=`<text class="xy-tick" x="${x(index)}" y="${bottom+27}" text-anchor="middle">${label}</text>`;}});
  svg+=`<text class="xy-axis-label" x="${(left+right)/2}" y="${bottom+57}" text-anchor="middle">${daily?'Ngày':'Tháng'} đăng tải</text>`;
  series.forEach(item=>{if(hidden.has(item.label))return;
    svg+=`<polyline class="trend-line" fill="none" stroke="${item.color}" stroke-width="3.5" points="${item.values.map((value,index)=>`${x(index)},${y(value)}`).join(' ')}"/>`;
    item.values.forEach((value,index)=>{const label=daily?periods[index].slice(8)+'/'+periods[index].slice(5,7):periods[index].slice(5,7)+'/'+periods[index].slice(0,4);
      svg+=`<circle class="trend-dot" data-chart-period="${periods[index]}" data-chart-series="${esc(item.label)}" data-chart-dimension="${dimension}" cx="${x(index)}" cy="${y(value)}" r="4.5" fill="white" stroke="${item.color}" stroke-width="2.5" tabindex="0" role="button" aria-label="Xem mã ${esc(item.label)} ngày ${label}"><title>${esc(item.label)} · ${label}: ${new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(value)}${unit} · bấm để xem mã</title></circle>`;
    });
  });
  series.forEach((item,index)=>{const xx=left+(index%3)*(span/3),yy=bottom+84+Math.floor(index/3)*30;
    svg+=`<g class="trend-legend${hidden.has(item.label)?' muted':''}" data-series="${esc(item.label)}" tabindex="0" role="button" aria-label="${hidden.has(item.label)?'Hiện':'Ẩn'} ${esc(item.label)}"><rect x="${xx}" y="${yy-10}" width="13" height="13" rx="3" fill="${item.color}"/><text x="${xx+20}" y="${yy+1}" fill="${item.color}">${esc(item.label.length>24?item.label.slice(0,23)+'…':item.label)}</text><title>${esc(item.label)} · bấm để ${hidden.has(item.label)?'hiện':'ẩn'} đường</title></g>`;
  });
  return {html:`<div class="xy-scroll">${svg}</svg></div>`,seriesCount:series.length,daily};
}
function renderMonthlyAnalysis() {
  const source=$('reportScope').value==='filtered'?state.filtered:state.rows;
  const months=[...new Set(source.map(reportMonth).filter(Boolean))].sort().reverse();
  const previous=$('reportMonth').value;
  $('reportMonth').innerHTML='<option value="">Tất cả tháng có dữ liệu</option>'+months.map(month=>`<option value="${month}">${month.slice(5)}/${month.slice(0,4)}</option>`).join('');
  $('reportMonth').value=months.includes(previous)?previous:'';
  const data=monthlyReport(source,$('reportMonth').value,$('reportKeyword').value);
  const n=data.rows.length;
  $('reportTotal').textContent=n;
  $('reportPlaces').textContent=data.locations.filter(item=>item.label!=='Chưa có địa điểm').length;
  $('reportInvestors').textContent=data.investors.length;
  $('reportInvestorBadge').textContent=n?`${data.knownInvestors}/${n} kết quả có tên`:'Chờ dữ liệu';
  $('reportCoverage').textContent=`${data.knownInvestors}/${n} kết quả có tên chủ đầu tư`;
  $('analysisSource').textContent=source.length?`${source.length} kết quả ${$('reportScope').value==='filtered'?'đang lọc':'trong truy vấn'} · Biểu đồ tự cập nhật`:'Biểu đồ tự cập nhật sau mỗi lần tìm kiếm';
  const knownStatuses=data.statuses.filter(item=>item.label!=='Chưa xác định');
  const knownForms=data.forms.filter(item=>item.label!=='Chưa có hình thức');
  state.reportDashboardRows=data.rows;
  state.reportChartItems={reportLocations:data.locations,
    reportInvestorChart:data.investors,reportStatuses:knownStatuses,reportForms:knownForms};
  reportColumns('reportLocations',data.locations,n);
  reportColumns('reportInvestorChart',data.investors,n);
  reportColumns('reportStatuses',knownStatuses,n);
  reportColumns('reportForms',knownForms,n);
  if(n&&!knownStatuses.length)$('reportStatuses').innerHTML='<p class="chart-empty">Chưa có trạng thái đấu thầu trong dữ liệu đã tải.</p>';
  if(n&&!knownForms.length)$('reportForms').innerHTML='<p class="chart-empty">Chưa có hình thức LCNT trong dữ liệu đã tải.</p>';
  const missingStatuses=n-knownStatuses.reduce((sum,item)=>sum+item.count,0);
  const missingForms=n-knownForms.reduce((sum,item)=>sum+item.count,0);
  $('reportStatusNote').textContent=n&&missingStatuses?state.mode==='Kế hoạch lựa chọn nhà thầu'?'KHLCNT là kế hoạch; trạng thái đấu thầu chỉ có ở TBMT.':`${missingStatuses} kết quả chưa có trạng thái xác định.`:'';
  $('reportFormNote').textContent=n&&missingForms?state.mode==='Kế hoạch lựa chọn nhà thầu'?'Quét nhanh KHLCNT chưa lấy hình thức từng gói. Tắt “Quét nhanh khi nhiều kết quả” rồi tìm lại nếu cần phân tích mục này.':`${missingForms} kết quả chưa có hình thức LCNT.`:'';
  $('reportStatusCard').classList.toggle('dashboard-card-unavailable',!knownStatuses.length);
  $('reportFormCard').classList.toggle('dashboard-card-unavailable',!knownForms.length);
  const unavailable=[];
  if(n&&!knownStatuses.length)unavailable.push(state.mode==='Kế hoạch lựa chọn nhà thầu'?'Trạng thái đấu thầu chỉ có ở TBMT':'Chưa có trạng thái đấu thầu');
  if(n&&!knownForms.length)unavailable.push('Chưa có hình thức LCNT trong dữ liệu đã tải');
  $('reportDataNote').textContent=unavailable.length?`Độ phủ dữ liệu · ${unavailable.join(' · ')}`:'';
  const dimension=$('reportDimension').value;
  const labels={locations:'địa điểm',groups:'nhóm mặt hàng',winners:'nhà thầu trúng',investors:'chủ đầu tư',statuses:'trạng thái',forms:'hình thức LCNT'};
  const terms=normalizeSearch($('reportKeyword').value).trim().split(/\s+/).filter(Boolean);
  const named=source.filter(row=>terms.every(term=>normalizeSearch(row.package_name||row.plan_name||'').includes(term)));
  state.reportTimelineRows=named;
  const timeline=reportTimelineChart(named,$('reportMonth').value,dimension,Number($('reportTop').value)||3,$('reportMeasure').value,state.reportHiddenSeries||new Set());
  $('reportFocusChart').innerHTML=timeline.html;
  $('reportFocusNote').textContent=`${timeline.daily?'Mỗi điểm là một ngày trong khoảng đang xem':'Mỗi điểm là một tháng có dữ liệu'} · ${timeline.seriesCount} đường ${dimension==='total'?'tổng kết quả':`theo ${labels[dimension]||'nhóm'}`}. ${$('reportMeasure').value==='percent'?'Tỷ lệ theo tổng kết quả của từng ngày/tháng; đường tổng thể tính theo toàn phạm vi.':'Đơn vị là số kết quả đã tải.'} Chọn tên đường bên dưới biểu đồ để ẩn hoặc hiện.`;
  const missingInvestors=n-data.knownInvestors;
  $('reportInvestorNote').textContent=!n?'Tên chủ đầu tư sẽ hiện ở đây sau khi có kết quả tra cứu.':!data.knownInvestors?'Các kết quả đã tải chưa có tên chủ đầu tư. Hãy kiểm tra cột Chủ đầu tư trong bảng kết quả.':missingInvestors?`${missingInvestors} kết quả chưa có tên chủ đầu tư. Mỗi kết quả được tính một lần cho chủ đầu tư của nó; biểu đồ hiển thị tối đa 10 đơn vị.`:`Đã có tên chủ đầu tư cho toàn bộ ${n} kết quả. Mỗi kết quả được tính một lần; biểu đồ hiển thị tối đa 10 đơn vị.`;
  $('analysisNote').textContent=`Báo cáo chỉ tính dữ liệu truy vấn đã tải, chưa đại diện toàn thị trường hoặc toàn tháng nếu giới hạn ngày/số trang. ${data.unknownDates} kết quả thiếu ngày đăng hợp lệ (không đưa vào từng tháng). Nhóm mặt hàng được nhận diện từ tên gói, ưu tiên generic → biệt dược → dược liệu → thiết bị → vật tư → thuốc khác. Biểu đồ địa điểm, chủ đầu tư và hình thức hiển thị top 10; tổng vẫn tính toàn bộ phạm vi. Tháng là tháng đăng tải.`;
}
$('monthlyAnalysis').addEventListener('click',event=>{
  const bar=event.target.closest('.xy-item[data-chart-id],.donut-legend-item[data-chart-id]');
  const point=event.target.closest('.trend-dot[data-chart-period]');
  if(bar)showBarCodes(bar);
  else if(point)showTrendCodes(point);
});
$('monthlyAnalysis').addEventListener('keydown',event=>{
  if(!['Enter',' '].includes(event.key))return;
  const target=event.target.closest('.xy-item[data-chart-id],.donut-legend-item[data-chart-id],.trend-dot[data-chart-period]');
  if(target){event.preventDefault();target.dispatchEvent(new MouseEvent('click',{bubbles:true}));}
});
$('chartSelectionList').addEventListener('click',event=>{
  const detail=event.target.closest('[data-chart-detail]');
  const table=event.target.closest('[data-chart-table]');
  if(detail)openDetail(Number(detail.dataset.chartDetail));
  if(table){
    const row=state.rows.find(item=>item.index===Number(table.dataset.chartTable));
    if(!row)return;
    clearViewFilters();$('quickFilter').value=reportCode(row);applyView();
    if(typeof showView==='function')showView('search');
    $('results').scrollIntoView?.({behavior:'smooth',block:'start'});
  }
});
$('copyChartCodes').addEventListener('click',async()=>{
  const codes=[...new Set((state.reportSelectedRows||[]).map(reportCode).filter(Boolean))];
  if(!codes.length)return;
  await copyText(codes.join('\n'));toast(`Đã sao chép ${codes.length} mã từ biểu đồ.`);
});
$('closeChartSelection').addEventListener('click',()=>$('chartSelection').classList.add('hidden'));
for(const id of ['reportScope','reportMonth'])$(id).addEventListener('change',renderMonthlyAnalysis);
for(const id of ['reportDimension','reportMeasure','reportTop'])$(id).addEventListener('change',event=>{if(event.target.id==='reportDimension')state.reportHiddenSeries=new Set();renderMonthlyAnalysis();});
let reportKeywordTimer;
$('reportKeyword').addEventListener('input',()=>{
  if(state.rows.length<=200){renderMonthlyAnalysis();return;}
  clearTimeout(reportKeywordTimer);
  reportKeywordTimer=setTimeout(renderMonthlyAnalysis,180);
});
$('reportFocusChart').addEventListener('click',event=>{const legend=event.target.closest('[data-series]');if(!legend)return;state.reportHiddenSeries??=new Set();const key=legend.dataset.series;state.reportHiddenSeries.has(key)?state.reportHiddenSeries.delete(key):state.reportHiddenSeries.add(key);renderMonthlyAnalysis();});
$('reportFocusChart').addEventListener('keydown',event=>{if(!['Enter',' '].includes(event.key))return;const legend=event.target.closest('[data-series]');if(legend){event.preventDefault();legend.dispatchEvent(new MouseEvent('click',{bubbles:true}));}});
$('downloadReportChart').addEventListener('click',async()=>{
  const chart=$('reportFocusChart').querySelector('svg');
  if(!chart)return toast('Chưa có biểu đồ để lưu.',true);
  const copy=chart.cloneNode(true);
  copy.setAttribute('xmlns','http://www.w3.org/2000/svg');
  const styles=getComputedStyle(document.body);
  const palette={'.xy-grid':`stroke:${styles.getPropertyValue('--line').trim()||'#dbe2f2'};stroke-dasharray:4 5`,'.xy-axis':`stroke:${styles.getPropertyValue('--muted').trim()||'#7789a7'};fill:none;stroke-width:1.3`,'.xy-tick, .xy-category':`fill:${styles.getPropertyValue('--ink').trim()||'#1f2b46'};font-size:13px`,'.xy-axis-label':`fill:${styles.getPropertyValue('--muted').trim()||'#7789a7'};font-size:13px;font-weight:600`,'.trend-legend text':'font-size:12px'};
  const style=document.createElementNS('http://www.w3.org/2000/svg','style');
  style.textContent=Object.entries(palette).map(([selector,rules])=>`${selector}{${rules}}`).join('');
  copy.prepend(style);
  const filename=`Bieu_do_${$('reportDimension').value}_${$('reportMonth').value||'tat_ca'}.svg`;
  await saveBlob(new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml;charset=utf-8'}),filename);
});
renderMonthlyAnalysis();
