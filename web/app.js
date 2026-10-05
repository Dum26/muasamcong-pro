const state = { rows: [], filtered: [], selected: new Set(), jobId: null, sourceCount: 0, searchVersion: 0, directory: null, mode: 'Thông báo mời thầu', extractFile: null, extractionId: null, extracted: [], extractedSelected: new Set(), lotsLoading: false, extractionSource: null, extractionVersion: 0, extractionStatus: 'done', extractionProcessed: 0 };
const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
function debounce(callback, delay=180) { let timer; return (...args)=>{clearTimeout(timer);timer=setTimeout(()=>callback(...args),delay);}; }
state.presets = [];
state.loading = false;
state.lotFiles = [];
state.lotIssues = [];
state.checkingLots = new Set();
state.autoLotPending = new Set();
state.page = 1;
state.watchlist = [];
state.history = null;
const rowSearchCache = new WeakMap();

function normalizeSearch(value) {
  return String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[đĐ]/g, 'd').toLowerCase();
}
function readLocal(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
function writeLocal(key, value) {
  try { localStorage.setItem(key, value); } catch { /* Browsing still works without local storage. */ }
}
function recentQueries() {
  if(Array.isArray(state.history))return state.history;
  return [];
}
function restoreQuery(x) {
  const mode=[...document.querySelectorAll('input[name="mode"]')].find(input=>input.value===x.mode);
  if(!mode)return;
  mode.checked=true; syncMode();
  for(const [id,key,fallback] of [['keyword','keyword',''],['dateFrom','date_from',''],['dateTo','date_to',''],['statusFilter','status','Tất cả trạng thái'],['pages','pages',5]]) $(id).value=String(x[key]??fallback);
  for(const [id,key,fallback] of [['useDates','use_dates',true],['detail','detail',false],['fastMode','fast_mode',false],['removeDuplicates','remove_duplicates',true]]) $(id).checked=x[key]??fallback;
  state.pendingFormFilter=String(x.bid_form||''); state.pendingLocationFilter=String(x.location||'');
  if(Array.from($('searchFormFilter').options||[]).some(option=>option.value===state.pendingFormFilter))$('searchFormFilter').value=state.pendingFormFilter;
  if(Array.from($('searchLocationFilter').options||[]).some(option=>option.value===state.pendingLocationFilter))$('searchLocationFilter').value=state.pendingLocationFilter;
}
async function loadPresets() {
  try { state.presets=(await (await api('/api/presets')).json()).presets; renderPresets(); }
  catch(error) { toast(error.message,true); }
}
function renderPresets(selected='') {
  $('savedPresets').innerHTML='<option value="">Chọn bộ tìm kiếm…</option>'+state.presets.filter(p=>p.params?.mode!=='Kho dữ liệu').map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  $('savedPresets').value=selected;
  syncPresetControls();
}
function syncPresetControls(){const preset=state.presets.find(item=>item.id===$('savedPresets').value);for(const id of ['pinPreset','watchPreset','renamePreset'])$(id).disabled=!preset;$('pinPreset').textContent=preset?.pinned?'Bỏ ghim':'Ghim';$('watchPreset').textContent=preset?.is_watch_enabled?'Tắt theo dõi':'Bật theo dõi';if(preset)$('presetName').value=preset.name;}
async function changePreset(action){const preset=state.presets.find(item=>item.id===$('savedPresets').value);if(!preset)return;const body={action,id:preset.id,name:$('presetName').value.trim(),pinned:!preset.pinned,enabled:!preset.is_watch_enabled};try{state.presets=(await (await api('/api/presets',{method:'POST',body:JSON.stringify(body)})).json()).presets||[];renderPresets(preset.id);toast(action==='watch'?(body.enabled?'Đã bật theo dõi bộ lọc.':'Đã tắt theo dõi bộ lọc.'):'Đã cập nhật bộ lọc.');}catch(error){toast(error.message,true);}}
async function updatePreset(action) {
  const name=$('presetName').value.trim(), id=$('savedPresets').value;
  if(action==='save'&&!name)return toast('Nhập tên bộ tìm kiếm trước khi lưu.',true);
  if(action==='delete'&&!id)return toast('Chọn bộ tìm kiếm cần xóa.',true);
  $('savePreset').disabled=true; $('deletePreset').disabled=true;
  try {
    state.presets=(await (await api('/api/presets',{method:'POST',body:JSON.stringify({action,name,id,params:searchParams()})})).json()).presets;
    renderPresets(action==='save'?state.presets[0].id:'');
    toast(action==='save'?'Đã lưu bộ tìm kiếm trên máy.':'Đã xóa bộ tìm kiếm.');
  } catch(error) { toast(error.message,true); }
  finally { $('savePreset').disabled=false; $('deletePreset').disabled=false; }
}
function applyPreset() {
  const preset=state.presets.find(p=>p.id===$('savedPresets').value);
  if(!preset)return toast('Chọn một bộ tìm kiếm đã lưu.',true);
  restoreQuery(preset.params); $('presetName').value=preset.name; toast('Đã áp dụng. Bấm Quét dữ liệu để tra cứu.');
}
function setDateRange(range) {
  const now=new Date(), from=new Date(now.getFullYear(),now.getMonth(),now.getDate());
  if(range==='month')from.setDate(1);
  else if(range!=='today')from.setDate(from.getDate()-Number(range)+1);
  $('dateFrom').value=userDate(from); $('dateTo').value=userDate(now); $('useDates').checked=true;
}
function syncViewOptions() {
  for(const [id,key,label] of [['viewStatus','tender_status','Tất cả trạng thái'],['viewLocation','location','Tất cả địa điểm']]) {
    const value=$(id).value;
    const values=[...new Set(state.rows.map(r=>key==='tender_status'?(r[key]||'Chưa xác định'):r[key]).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'vi'));
    $(id).innerHTML=`<option value="">${label}</option>`+values.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
    $(id).value=values.includes(value)?value:'';
  }
  for(const [id,key,label] of [['searchFormFilter','bid_form','Tất cả hình thức'],['searchLocationFilter','location','Tất cả địa điểm']]) {
    const value=$(id).value;
    const values=[...new Set(state.rows.map(row=>row[key]).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'vi'));
    $(id).innerHTML=`<option value="">${label}</option>`+values.map(item=>`<option value="${esc(item)}">${esc(item)}</option>`).join('');
    const desired=id==='searchFormFilter'?state.pendingFormFilter:state.pendingLocationFilter;
    $(id).value=values.includes(desired)?desired:values.includes(value)?value:'';
  }
}
function clearViewFilters() {
  for(const id of ['quickFilter','viewStatus','viewLocation','viewDeadline'])$(id).value='';
  $('sortBy').value='default'; applyView();
}
function deadlineHours(row, now=Date.now()) {
  if(row.tender_status!=='Chưa đóng thầu')return null;
  const timestamp=parseViDate(row.bid_close_date);
  return timestamp?(timestamp-now)/3600000:null;
}
function deadlineBadge(row) {
  const hours=deadlineHours(row);
  if(hours===null||hours<=0||hours>72)return '';
  const label=hours<1?'Còn dưới 1 giờ':hours<=24?`Còn ${Math.ceil(hours)} giờ`:`Còn ${Math.ceil(hours/24)} ngày`;
  return `<span class="deadline-badge ${hours<=24?'urgent':''}">${label}</span>`;
}

function toast(message, error=false) {
  const item = document.createElement('div'); item.className = `toast animate-in fade-in duration-200${error ? ' error' : ''}`; item.textContent = message;
  $('toastStack').appendChild(item); setTimeout(() => item.remove(), 4200);
}
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement('textarea'); area.value = text; area.style.position = 'fixed'; area.style.opacity = '0';
    document.body.appendChild(area); area.select(); document.execCommand('copy'); area.remove();
  }
}
function userDate(date) { const y=date.getFullYear(), m=String(date.getMonth()+1).padStart(2,'0'), d=String(date.getDate()).padStart(2,'0'); return `${d}/${m}/${y}`; }
function initDates() { const now = new Date(); $('dateTo').value = userDate(now); $('dateFrom').value = userDate(new Date(now.getFullYear(), now.getMonth(), 1)); }

function currentMode() { return document.querySelector('input[name="mode"]:checked').value; }
function syncMode() {
  state.mode = currentMode(); const notice = state.mode === 'Thông báo mời thầu';
  document.body.classList.toggle('notice-mode', notice);
  $('statusField').classList.toggle('hidden', !notice); $('keyword').placeholder = notice ? 'Ví dụ: thuốc generic, thiết bị y tế, IB260…' : 'Nhập tên dự án, tên gói hoặc mã PL…';
  $('searchButton').querySelector('span').textContent = notice ? 'Quét dữ liệu' : 'Tìm kế hoạch';
  renderStats();
}

async function api(path, options={}) {
  const response = await fetch(path, {headers:{'Content-Type':'application/json'}, ...options});
  if (!response.ok) { let data={}; try { data=await response.json(); } catch {} throw new Error(data.error || `Lỗi HTTP ${response.status}`); }
  return response;
}

function searchParams() { return {
  mode: currentMode(), keyword: $('keyword').value.trim(), use_dates: $('useDates').checked,
  date_from: $('dateFrom').value, date_to: $('dateTo').value, status: $('statusFilter').value,
  pages: Number($('pages').value), detail: $('detail').checked, fast_mode: $('fastMode').checked,
  remove_duplicates: $('removeDuplicates').checked,
  bid_form: $('searchFormFilter').value, location: $('searchLocationFilter').value
}; }

async function startSearch(event, forceRefresh=false) {
  event?.preventDefault(); const params = searchParams();
  state.lastSearchParams=params;
  state.mode=params.mode;
  if (!params.keyword && params.mode !== 'Thông báo mời thầu') return toast('Hãy nhập từ khóa hoặc mã KHLCNT.', true);
  if (!params.keyword && !params.use_dates) return toast('Quét TBMT không có từ khóa cần bật lọc theo ngày.', true);
  state.searchState='loading';
  const version=++state.searchVersion;
  state.jobId=null; state.checkingLots=new Set(); state.autoLotPending=new Set(); clearExtraction();
  state.lotFiles=[]; state.lotIssues=[]; state.lotRequested=0; renderLotDownloads();
  setLoading(true, 'Đang khởi tạo truy vấn…'); state.rows=[]; state.sourceCount=0; state.filtered=[]; state.selected.clear(); render(true);
  try {
    const response = await api('/api/search', {method:'POST', body:JSON.stringify({...params,force_refresh:forceRefresh})}); const job = await response.json();
    if(version!==state.searchVersion)return;
    state.jobId = job.id;
    saveRecent(params); await pollJob(job.id);
  } catch (error) { if(version===state.searchVersion){state.searchState='error';state.searchError=error.message;setLoading(false);$('resultMeta').innerHTML=`<span class="data-error">Không lấy được dữ liệu: ${esc(error.message)}</span> · <button type="button" data-retry-search>Thử lại</button>`;toast(error.message, true);} }
}

async function pollJob(id) {
  while (state.jobId === id) {
    try {
      const response = await api(`/api/job?id=${encodeURIComponent(id)}`); const job = await response.json();
      if(state.jobId!==id)return;
      $('progressText').textContent = job.message;
      if (job.state === 'done') { state.rows = job.rows || []; state.sourceCount=job.source_count||state.rows.length; state.lastFetchedAt=job.fetched_at||new Date().toISOString(); state.searchState='ok';state.page=1; state.selected.clear(); syncViewOptions(); applyView(); setLoading(false); $('resultMeta').textContent = `Hoàn tất · ${new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'})} · ${state.sourceCount} kết quả từ e-GP`; toast(`Đã tìm thấy ${state.rows.length} dòng kết quả.`); if(state.rows.length)showView('search'); if(typeof syncWatchlistAfterSearch==='function')void syncWatchlistAfterSearch(); if(typeof completeHistorySearch==='function')void completeHistorySearch(state.lastSearchParams,state.sourceCount); if(typeof openPendingDetail==='function')openPendingDetail(); return; }
      if (job.state === 'error') throw new Error(job.error || job.message);
      await new Promise(resolve => setTimeout(resolve, 650));
    } catch (error) { if(state.jobId===id){state.searchState='error';state.searchError=error.message;setLoading(false); $('resultMeta').innerHTML=`<span class="data-error">Không lấy được dữ liệu: ${esc(error.message)}</span> · <button type="button" data-retry-search>Thử lại</button>`; toast(error.message, true);} return; }
  }
}

function setLoading(active, message='') {
  state.loading=active;
  const button=$('searchButton');
  button.disabled=active;
  button.classList.toggle('is-loading',active);
  button.setAttribute('aria-busy',String(active));
  button.querySelector('span').textContent=active?'Đang tra cứu…':state.mode==='Thông báo mời thầu'?'Quét dữ liệu':'Tìm kế hoạch';
  $('progressWrap').classList.toggle('hidden', !active);
  $('refreshData').disabled=active;
  if(message) $('progressText').textContent=message;
  updateEmptyState();
}
function updateEmptyState() {
  const title=state.loading?'Đang tìm dữ liệu…':state.searchState==='error'?'Không lấy được dữ liệu':state.rows.length?'Không có kết quả khớp bộ lọc':state.searchState==='ok'?'Không tìm thấy kết quả':'Bắt đầu một truy vấn mới';
  const hint=state.searchState==='error'?'Kiểm tra kết nối e-GP và bấm “Thử lại” ở phía trên.':state.rows.length?'Thử xóa lọc bảng hoặc thay đổi điều kiện lọc.':state.searchState==='ok'?'Thử từ khóa, ngày đăng hoặc bộ lọc khác.':'Chọn khoảng ngày và nhấn “Quét dữ liệu” để xem kết quả.';
  $('emptyState').querySelector('h3').textContent=title;
  $('emptyState').querySelector('p').textContent=hint;
}
function statusClass(status='') { if(status.includes('Chưa đóng')) return 'status-open'; if(status.includes('Đang xét')) return 'status-review'; if(status.includes('hủy') || status.includes('vô hiệu') || status.includes('Không công nhận')) return 'status-cancel'; if(status.includes('trúng')) return 'status-result'; return ''; }
function lotFileLabel(row) {
  if(row.has_lots || row.lot_file_status==='done')return 'Có file';
  if(['Ko co file','Không có file'].includes(row.lot_file_status))return 'Không có file';
  if(row.lot_file_status==='Chưa kiểm tra được')return 'Lỗi kiểm tra';
  return 'Chưa kiểm tra';
}
function resultColumnText(key) {
  return state.filtered.map((row,index)=>{
    if(key==='__stt')return String(index+1);
    if(key==='__code')return row.notify_no||planDisplayCode(row);
    if(key==='__lot_file')return lotFileLabel(row);
    if(key==='__tracking')return state.watchlist.some(item=>item.code===(row.notify_no||planDisplayCode(row)))?'Đang theo dõi':'';
    if(key==='__price')return row.package_price||'Chưa có dữ liệu';
    return String(row[key]??'');
  }).map(value=>value.replace(/[\t\r\n]+/g,' ')).join('\n');
}
async function activateResultHeader(th, sortInstead=false) {
  if(!state.filtered.length)return toast('Chưa có dữ liệu trong cột để sao chép.',true);
  const key=th.dataset.copy;
  if(sortInstead) {
    if(['__lot_file','__tracking','__price','__stt'].includes(key))return toast('Cột này không hỗ trợ sắp xếp.',true);
    state.headerSort={key,descending:state.headerSort?.key===key?!state.headerSort.descending:false};
    state.page=1;applyView();
    return;
  }
  await copyText(resultColumnText(key));
  toast(`Đã sao chép cột ${th.textContent.trim()} · ${state.filtered.length} dòng đang lọc.`);
}
function planDisplayCode(row) {
  if(row.plan_no)return 'PL'+String(row.plan_no).replace(/^PL/i,'').replace(/-\d+$/,'');
  return String(row.plan_reference||'').replace(/-\d+$/,'');
}
function officialDetailUrl(row) {
  const url=String(row.source_url||'');
  return /^https:\/\/muasamcong\.mpi\.gov\.vn\/web\/guest\/contractor-selection\?/.test(url)?url:'';
}
function packageNameCell(row) {
  const name=esc(row.package_name||row.plan_name||'—');
  const url=officialDetailUrl(row);
  return url?`<a class="package-name package-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer" title="Mở trên e-GP: ${name}">${name}<span aria-hidden="true"> ↗</span></a>`:
    `<button type="button" class="package-name package-link package-detail" data-detail="${row.index}" title="Xem chi tiết: ${name}">${name}</button>`;
}
function parseViDate(value='') {
  const m=String(value).match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$/);
  if(!m)return 0;
  const day=+m[1], month=+m[2], year=+m[3], hour=+(m[4]||0), minute=+(m[5]||0), second=+(m[6]||0);
  const date=new Date(Date.UTC(year,month-1,day,hour,minute,second));
  if(date.getUTCFullYear()!==year||date.getUTCMonth()!==month-1||date.getUTCDate()!==day||hour>23||minute>59||second>59)return 0;
  return date.getTime()-7*3600000;
}

function applyView() {
  const terms=normalizeSearch($('quickFilter').value).trim().split(/\s+/).filter(Boolean);
  const status=$('viewStatus').value, location=$('viewLocation').value, deadline=Number($('viewDeadline').value), now=Date.now();
  const form=$('searchFormFilter').value, searchLocation=$('searchLocationFilter').value;
  let rows=state.rows.filter(r => {
    if(status&&(r.tender_status||'Chưa xác định')!==status)return false;
    if(location&&r.location!==location)return false;
    if(form&&r.bid_form!==form)return false;
    if(searchLocation&&r.location!==searchLocation)return false;
    if(deadline) { const hours=deadlineHours(r,now); if(hours===null||hours<=0||hours>deadline)return false; }
    let text=rowSearchCache.get(r);
    if(text===undefined){text=normalizeSearch(Object.values(r).filter(v=>typeof v==='string').join(' '));rowSearchCache.set(r,text);}
    return terms.every(term=>text.includes(term));
  });
  const sort=$('sortBy').value; if(sort==='close') rows.sort((a,b)=>(parseViDate(a.bid_close_date)||Infinity)-(parseViDate(b.bid_close_date)||Infinity));
  if(sort==='default')rows.sort((a,b)=>(parseViDate(a.public_date)||Number.MAX_SAFE_INTEGER)-(parseViDate(b.public_date)||Number.MAX_SAFE_INTEGER));
  if(sort==='newest')rows.sort((a,b)=>(parseViDate(b.public_date)||-1)-(parseViDate(a.public_date)||-1));
  if(sort==='location') rows.sort((a,b)=>(a.location||'').localeCompare(b.location||'','vi')); if(sort==='status') rows.sort((a,b)=>(a.tender_status||'').localeCompare(b.tender_status||'','vi'));
  if(state.headerSort) {
    const {key,descending}=state.headerSort;
    rows.sort((a,b)=>{
      const av=key==='__code'?(a.notify_no||planDisplayCode(a)):a[key]||'';
      const bv=key==='__code'?(b.notify_no||planDisplayCode(b)):b[key]||'';
      const dateKey=['public_date','bid_close_date'].includes(key);
      const result=dateKey?(parseViDate(av)||Infinity)-(parseViDate(bv)||Infinity):String(av).localeCompare(String(bv),'vi',{numeric:true});
      return descending?-result:result;
    });
  }
  const changed=rows.length!==state.filtered.length||rows.some((row,index)=>row.index!==state.filtered[index]?.index);
  if(changed&&state.extractionSource==='results')clearExtraction();
  state.filtered=rows;
  state.page=Math.max(1,Math.min(state.page||1,Math.ceil(rows.length/Number($('pageSize').value))||1));
  const visibleIndices=new Set(rows.map(row=>row.index));
  state.selected=new Set([...state.selected].filter(index=>visibleIndices.has(index)));
  render(changed);
}

function render(updateAnalysis=false) {
  if(updateAnalysis&&typeof renderMonthlyAnalysis==='function')renderMonthlyAnalysis();
  renderStats(); const body=$('resultBody'); const size=Number($('pageSize').value)||50; const pageCount=Math.max(1,Math.ceil(state.filtered.length/size)); state.page=Math.max(1,Math.min(state.page||1,pageCount)); const start=(state.page-1)*size; const pageRows=state.filtered.slice(start,start+size);
  body.innerHTML=pageRows.map((r,i)=>`<tr class="${state.selected.has(r.index)?'selected':''}" data-index="${r.index}">
    <td class="check-col"><input class="row-check" type="checkbox" data-index="${r.index}" ${state.selected.has(r.index)?'checked':''}></td>
    <td>${start+i+1}</td><td><button class="code copy-cell" data-copy-value="${esc(r.notify_no || planDisplayCode(r))}" title="Sao chép mã">${esc(r.notify_no || planDisplayCode(r))}</button>${r.notify_no&&r.plan_no?`<span class="subcode">${esc(planDisplayCode(r))}</span>`:''}${r.package_no?`<span class="subcode" title="Chỉ tải phân lô của gói này">${esc(r.package_no)}</span>`:''}</td><td><button class="watch-toggle ${state.watchlist.some(item=>item.code===(r.notify_no||planDisplayCode(r)))?'is-watched':''}" data-watch="${r.index}" title="Theo dõi gói"><i data-lucide="star" aria-hidden="true"></i> ${state.watchlist.some(item=>item.code===(r.notify_no||planDisplayCode(r)))?'Đang theo dõi':'Theo dõi'}</button></td>
    <td class="lot-availability"><span class="status-badge ${lotFileLabel(r)==='Có file'?'status-open':lotFileLabel(r)==='Không có file'?'status-cancel':''}">${state.checkingLots.has(r.index)?'Đang kiểm tra…':state.autoLotPending.has(r.index)?'Đang chờ kiểm tra…':lotFileLabel(r)}</span>${!['Có file','Không có file'].includes(lotFileLabel(r))&&!state.autoLotPending.has(r.index)?`<button type="button" class="lot-recheck" data-check-lot="${r.index}" ${state.checkingLots.has(r.index)?'disabled':''} title="Kiểm tra lại file phân lô của dòng này">Thử lại</button>`:''}</td>
    <td><span class="status-badge ${statusClass(r.tender_status)}">${esc(r.tender_status||'Chưa xác định')}</span></td><td>${esc(r.bid_close_date||'—')}${deadlineBadge(r)}</td>
    <td>${esc(r.location||'—')}</td><td>${packageNameCell(r)}</td>
    <td><span class="investor-name" title="${esc(r.investor_name||'Chưa có chủ đầu tư')}">${esc(r.investor_name||'—')}</span></td><td class="muted-small" title="${r.package_price?'Giá từ e-GP':'Nguồn chưa cung cấp giá'}">${esc(r.package_price||'—')}</td><td>${esc(r.winner||'—')}</td>
    <td>${esc(r.bid_form||'—')}</td><td>${esc(r.public_date||'—')}</td><td><button class="row-more" type="button" data-row-menu="${r.index}" aria-label="Thao tác với ${esc(r.notify_no||planDisplayCode(r))}" aria-haspopup="menu" aria-expanded="false"><i data-lucide="ellipsis" aria-hidden="true"></i></button></td></tr>`).join('');
  $('emptyState').classList.toggle('hidden', state.filtered.length>0||state.loading); $('resultCount').textContent=state.filtered.length; $('selectionText').textContent=state.selected.size?`Đã chọn ${state.selected.size} dòng · Bấm tiêu đề để sao chép cột`:'Bấm tiêu đề để sao chép cột · Shift + bấm để sắp xếp';
  $('compareTenders').disabled=state.selected.size<2||state.selected.size>5;
  const noticeCount=state.filtered.filter(row=>row.notify_no).length; $('extractFromResults').textContent=noticeCount?`Lấy ${noticeCount} mã đang lọc`:'Lấy mã từ kết quả đang lọc';
  $('pageText').textContent=`Hiển thị ${state.filtered.length?start+1:0}–${Math.min(start+size,state.filtered.length)} / ${state.filtered.length} kết quả`;
  $('paginationSummary').textContent=`Trang ${state.page} / ${pageCount}`; $('prevPage').disabled=state.page<=1; $('nextPage').disabled=state.page>=pageCount;
  $('viewSummary').textContent=`Đang hiển thị ${state.filtered.length} / ${state.rows.length} kết quả · Đã chọn ${state.selected.size}`;
  const urgent=state.filtered.filter(r=>{const hours=deadlineHours(r);return hours!==null&&hours>0&&hours<=72;}).length;
  $('deadlineSummary').textContent=urgent?`${urgent} gói đóng thầu trong 3 ngày tới · Giờ Việt Nam`:'Hạn đóng thầu theo giờ Việt Nam';
  updateEmptyState();
  const visible=pageRows.map(r=>r.index); $('selectAll').checked=visible.length>0&&visible.every(i=>state.selected.has(i)); $('selectAll').indeterminate=visible.some(i=>state.selected.has(i))&&!visible.every(i=>state.selected.has(i));
}

function renderStats() {
  const rows=state.rows, notice=state.mode==='Thông báo mời thầu';
  $('statTotal').textContent=notice?(state.sourceCount||rows.length):0;
  $('statTotalHint').textContent=rows.length?(state.sourceCount&&state.sourceCount!==rows.length?`${rows.length} dòng đã tải vào bảng`:'Kết quả từ e-GP'):'Chưa có truy vấn';
  $('statPlans').textContent=notice?new Set(rows.map(planDisplayCode).filter(Boolean)).size:(state.sourceCount||rows.length);
  $('statTracked').textContent=state.watchlist.length;
  $('statOpenLabel').textContent='Chưa đóng thầu'; $('statOpenHint').textContent='Còn trước thời điểm đóng';
  $('statReviewLabel').textContent='Đang xét thầu'; $('statReviewHint').textContent='Đã mở và đang đánh giá';
  $('statResultLabel').textContent='Gói có KQLCNT'; $('statResultHint').textContent='Theo trạng thái thông báo';
  $('statOpen').textContent=rows.filter(r=>r.tender_status==='Chưa đóng thầu').length;
  $('statReview').textContent=rows.filter(r=>r.tender_status==='Đang xét thầu').length;
  $('statResult').textContent=rows.filter(r=>r.tender_status==='Có nhà thầu trúng thầu'||r.winner).length;
}
function toggleRow(index, checked) { checked?state.selected.add(index):state.selected.delete(index); render(); }
function selectionIndices() { return [...state.selected]; }

async function chooseFolder() {
  if (!window.showDirectoryPicker) { toast('Trình duyệt này chưa hỗ trợ chọn thư mục. File sẽ vào thư mục Tải xuống.', true); return; }
  try { state.directory=await window.showDirectoryPicker({mode:'readwrite'}); $('folderName').textContent=state.directory.name; $('folderHint').textContent='Các file Excel sẽ được lưu trực tiếp tại đây.'; $('folderState').textContent='Đã cấp quyền ghi'; toast(`Đã chọn thư mục ${state.directory.name}.`); } catch(error) { if(error.name!=='AbortError') toast(error.message,true); }
}
async function saveBlob(blob, filename, quiet=false) {
  if(state.directory) {
    try {
      let name=filename, number=2;
      while(true) {
        try { await state.directory.getFileHandle(name); }
        catch(error) { if(error.name==='NotFoundError')break; throw error; }
        const dot=filename.lastIndexOf('.');
        name=dot>0?`${filename.slice(0,dot)} (${number++})${filename.slice(dot)}`:`${filename} (${number++})`;
      }
      const handle=await state.directory.getFileHandle(name,{create:true}); const writable=await handle.createWritable();
      await writable.write(blob); await writable.close(); if(!quiet)toast(`Đã lưu ${name} vào ${state.directory.name}.`); return 'folder';
    } catch(error) { toast(`Không ghi được thư mục đã chọn: ${error.message}`,true); }
  }
  const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download=filename; a.click(); setTimeout(()=>URL.revokeObjectURL(url),60000); if(!quiet)toast(`Đã gửi ${filename} tới trình duyệt.`); return 'browser';
}
function responseFilename(response, fallback) { return response.headers.get('X-Filename')||fallback; }
async function download(path, selectedOnly, fallback) {
  if(!state.jobId||!state.filtered.length) return toast('Chưa có dữ liệu để tải.',true);
  const indices=state.filtered.filter(row=>!selectedOnly||state.selected.has(row.index)).map(row=>row.index);
  if(!indices.length) return toast('Hãy chọn ít nhất một dòng trong kết quả đang lọc.',true);
  if(path==='/api/lots')return downloadLotSelection({job_id:state.jobId,indices},indices.length);
  const task=typeof beginDownloadTask==='function'?beginDownloadTask(fallback,'Excel kết quả'):null;
  try { const response=await api(path,{method:'POST',body:JSON.stringify({job_id:state.jobId,indices})}); await saveBlob(await response.blob(),responseFilename(response,fallback)); if(typeof finishDownloadTask==='function')finishDownloadTask(task); } catch(error) { if(typeof failDownloadTask==='function')failDownloadTask(task,error); toast(error.message,true); }
}
async function downloadLotSelection(payload, count, saveFiles=true) {
  if(state.lotsLoading)return;
  if(!count)return toast('Hãy tick ít nhất một mã để tải phân lô.',true);
  state.lotsLoading=true; $('downloadLots').disabled=true; renderExtraction();
  const task=typeof beginDownloadTask==='function'?beginDownloadTask(`Phân lô · ${count} gói`,'Excel phân lô'):null;
  state.lotFiles=[]; state.lotIssues=[]; state.lotRequested=count; renderLotDownloads();
  const progress=`Đang lấy phân lô của ${count} mã…`;
  $('downloadLots').textContent=progress; toast(progress);
  try {
    const response=await api('/api/lots',{method:'POST',body:JSON.stringify(payload)});
    const result=await response.json();
    state.lotFiles=result.files||[]; state.lotIssues=result.issues||[];
    state.lotRequested=result.requested||count;
    if(payload.job_id===state.jobId) {
      for(const check of result.checks||[]) {
        const row=state.rows.find(row=>row.index===check.index);
        if(row){row.lot_file_status=check.lot_file_status;row.has_lots=check.has_lots;rowSearchCache.delete(row);}
      }
      render();
    }
    renderLotDownloads();
    $('lotDownloads').scrollIntoView({behavior:'smooth',block:'nearest'});
    if(saveFiles&&state.lotFiles.length)await saveLotFiles();
    else if(!state.lotFiles.length)toast('Không tạo file Excel. Xem lý do của từng mã bên dưới.',true);
    else toast(`Đã phân tích ${state.lotFiles.length} gói.${state.lotIssues.length?' Có mã lỗi; xem danh sách file.':''}`);
    if(typeof finishDownloadTask==='function')finishDownloadTask(task);
  } catch(error) { if(typeof failDownloadTask==='function')failDownloadTask(task,error); toast(error.message,true); }
  finally { state.lotsLoading=false; $('downloadLots').disabled=false; $('downloadLots').textContent='Tải Excel phân lô'; renderExtraction(); renderLotDownloads(); }
}
async function checkLot(index,quiet=false,jobId=state.jobId) {
  if(!jobId || state.jobId!==jobId || state.checkingLots.has(index))return;
  const checking=state.checkingLots;
  checking.add(index); render();
  try {
    const response=await api('/api/check-lot',{method:'POST',body:JSON.stringify({job_id:jobId,index})});
    const result=await response.json();
    if(state.jobId!==jobId)return;
    const row=state.rows.find(item=>item.index===index);
    if(row) { row.lot_file_status=result.lot_file_status; row.has_lots=result.has_lots; rowSearchCache.delete(row); }
    if(!quiet) {
      if(result.reason)toast(`Chưa xác minh được file: ${result.reason}`,true);
      else toast(result.has_lots?'Gói này có file phân lô.':'Gói này không có file phân lô.');
    }
  } catch(error) { if(state.jobId===jobId){const row=state.rows.find(item=>item.index===index);if(row){row.lot_file_status='Chưa kiểm tra được';row.has_lots=false;rowSearchCache.delete(row);}if(!quiet)toast(`Kiểm tra file thất bại: ${error.message}`,true);} }
  finally { checking.delete(index); if(state.jobId===jobId)render(); }
}
async function checkNoticeLotsAutomatically(jobId) {
  if(state.mode!=='Thông báo mời thầu'||state.jobId!==jobId)return;
  const pending=state.rows.filter(row=>!['Có file','Không có file'].includes(lotFileLabel(row))).map(row=>row.index);
  if(!pending.length)return;
  const autoPending=state.autoLotPending=new Set(pending);render();
  let next=0, completed=0;
  const workers=Array.from({length:Math.min(4,pending.length)},async()=>{
    while(state.jobId===jobId && next<pending.length) {
      const index=pending[next++];
      await checkLot(index,true,jobId);
      autoPending.delete(index);
      completed++;
      if(state.jobId===jobId){render();$('resultMeta').textContent=`Đang kiểm tra file phân lô ${completed}/${pending.length} · ${state.sourceCount} kết quả từ e-GP`;}
    }
  });
  await Promise.all(workers);
  if(state.jobId===jobId){
    const unresolved=pending.filter(index=>{const row=state.rows.find(item=>item.index===index);return row&&!['Có file','Không có file'].includes(lotFileLabel(row));}).length;
    $('resultMeta').textContent=`Kiểm tra file phân lô: ${pending.length-unresolved}/${pending.length} đã xác minh${unresolved?` · ${unresolved} lỗi có thể thử lại`:''} · ${state.sourceCount} kết quả từ e-GP`;
  }
}
function renderLotDownloads() {
  $('lotDownloads').classList.toggle('hidden',!state.lotFiles.length&&!state.lotIssues.length);
  $('lotDownloadSummary').textContent=`Lần tải gần nhất: ${state.lotRequested||state.lotFiles.length} dòng đã chọn · ${state.lotFiles.length} file Excel · ${state.lotIssues.length} dòng không xuất được`;
  $('saveAllLotFiles').disabled=state.lotsLoading||!state.lotFiles.length;
  $('lotFileList').innerHTML=state.lotFiles.map(file=>`<li><a href="${esc(file.url)}" download="${esc(file.name)}"><i data-lucide="download" aria-hidden="true"></i> ${esc(file.name)}</a><span class="${file.error?'file-error':''}">${esc(file.error||file.status||'Sẵn sàng tải')}</span></li>`).join('');
  $('lotIssueList').innerHTML=state.lotIssues.map(issue=>`<li>${esc(issue.code)}: ${esc(issue.reason)}</li>`).join('');
}
async function saveLotFiles() {
  let saved=0, sent=0, failed=0;
  for(const [index,file] of state.lotFiles.entries()) {
    $('downloadLots').textContent=`Đang tải file ${index+1}/${state.lotFiles.length}…`;
    try {
      const response=await api(file.url);
      const destination=await saveBlob(await response.blob(),file.name,true);
      file.error='';
      if(destination==='folder'){saved++;file.status='Đã lưu vào thư mục';}
      else {sent++;file.status='Đã gửi trình duyệt';}
    } catch(error) { failed++; file.error=error.message; }
    renderLotDownloads();
  }
  toast(`${saved?`Đã lưu ${saved} file Excel. `:''}${sent?`Đã gửi ${sent} file tới trình duyệt. `:''}${failed?`${failed} file lỗi; bấm tên file để thử lại. `:''}${state.lotIssues.length?`${state.lotIssues.length} mã không lấy được phân lô; xem danh sách bên dưới.`:''}`,failed>0);
}
async function retryLotFiles() {
  if(state.lotsLoading||!state.lotFiles.length)return;
  state.lotsLoading=true; $('downloadLots').disabled=true; renderExtraction(); renderLotDownloads();
  try { await saveLotFiles(); }
  finally {state.lotsLoading=false;$('downloadLots').disabled=false;$('downloadLots').textContent='Tải Excel phân lô';renderExtraction();renderLotDownloads();}
}
function extractedSelectionIndices() { return state.extracted.map((row,index)=>index).filter(index=>state.extractedSelected.has(index)); }
function selectAllExtracted(checked) { state.extractedSelected=checked?new Set(state.extracted.map((row,index)=>index)):new Set(); renderExtraction(); }
async function downloadExtractedLots() {
  if(!state.extractionId)return toast('Hãy tra cứu danh sách mã trước.',true);
  const indices=extractedSelectionIndices().filter(index=>state.extracted[index]?.code?.startsWith('IB'));
  if(!indices.length)return toast('Hãy chọn mã TBMT (IB) để tải file phân lô.',true);
  return downloadLotSelection({extraction_id:state.extractionId,indices},indices.length);
}
function openDetail(index) { const row=state.rows.find(r=>r.index===index); if(!row)return; $('drawerCode').textContent=row.notify_no||planDisplayCode(row); const fields=[['Tên gói thầu',row.package_name],['Tên kế hoạch / dự án',row.plan_name],['Trạng thái',row.tender_status],['Thời điểm đóng thầu',row.bid_close_date],['Tỉnh / Thành phố',row.location],['Hình thức LCNT',row.bid_form],['Chủ đầu tư',row.investor_name],['Nhà thầu trúng',row.winner],['Ngày đăng tải',row.public_date],['Ngày phê duyệt',row.decision_date],['Danh sách phân lô',lotFileLabel(row)]]; $('drawerBody').innerHTML=fields.map(([k,v])=>`<div class="detail-item"><span>${esc(k)}</span><strong>${esc(v||'—')}</strong></div>`).join(''); $('detailDrawer').classList.add('open'); $('drawerBackdrop').classList.add('open'); $('detailDrawer').setAttribute('aria-hidden','false'); }
function closeDetail(){ $('detailDrawer').classList.remove('open'); $('drawerBackdrop').classList.remove('open'); $('detailDrawer').setAttribute('aria-hidden','true'); }

function saveRecent(params) { const list=recentQueries(); const item={...params,time:Date.now()}; const key=JSON.stringify(params); state.history=[item,...list.filter(({time,...x})=>JSON.stringify(x)!==key)].slice(0,30); renderRecent(); }
function renderRecent() { const list=recentQueries(); $('recentList').innerHTML=list.length?list.map((x,i)=>`<button class="recent-item" data-recent="${i}" title="${esc(x.keyword||'Tất cả TBMT')}">${esc(x.keyword||'Tất cả TBMT')} · ${esc(x.date_from||'')} → ${esc(x.date_to||'')}</button>`).join(''):'<span class="muted-small">Chưa có lịch sử</span>'; }
function loadRecent(index) { const x=recentQueries()[index]; if(!x)return; restoreQuery(x); toast('Đã nạp lại đầy đủ tùy chọn truy vấn.'); }
 function resetSearch(){ $('keyword').value=''; $('statusFilter').value='Tất cả trạng thái'; $('pages').value='5'; $('detail').checked=false; $('fastMode').checked=false; $('removeDuplicates').checked=true; $('useDates').checked=true; $('searchFormFilter').value=''; $('searchLocationFilter').value=''; state.pendingFormFilter='';state.pendingLocationFilter='';initDates();applyView(); }

function setExtractFile(file) {
  clearExtraction();
  state.extractFile = file || null;
  $('extractFileName').textContent = file ? `${file.name} · ${(file.size/1024).toFixed(1)} KB` : 'Chưa chọn tệp';
}
async function fileBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer()); let binary = '';
  for(let index=0; index<bytes.length; index+=32768) binary += String.fromCharCode(...bytes.subarray(index,index+32768));
  return btoa(binary);
}
function clearExtraction() {
  state.extractionVersion++; state.extractionId=null; state.extracted=[]; state.extractedSelected.clear(); state.extractionSource=null; state.extractionStatus='done'; state.extractionProcessed=0; renderExtraction();
}
async function submitExtraction(payload, source='input') {
  clearExtraction(); const version=state.extractionVersion; state.extractionSource=source;
  const response=await api('/api/extract',{method:'POST',body:JSON.stringify(payload)}); let result=await response.json();
  while(version===state.extractionVersion) {
    state.extractionId=result.id; state.extracted=result.rows||[]; state.extractionStatus=result.state||'done'; state.extractionProcessed=result.processed||0; renderExtraction();
    if(state.extractionStatus==='done') { toast(`Đã lấy thông tin ${state.extracted.length} mã TBMT/KHLCNT.`); return; }
    await new Promise(resolve=>setTimeout(resolve,650));
    if(version!==state.extractionVersion)return;
    result=await (await api(`/api/extraction?id=${encodeURIComponent(result.id)}`)).json();
  }
}
async function runExtraction() {
  const text = $('extractText').value;
  if(!state.extractFile && !text.trim()) return toast('Hãy chọn file hoặc dán dữ liệu cần tách mã.',true);
  const button=$('runExtract'); button.disabled=true; button.querySelector('span').textContent='Đang phân tích…';
  try {
    const payload={text,remove_duplicates:$('extractDeduplicate').checked,filename:state.extractFile?.name||'',file_base64:state.extractFile?await fileBase64(state.extractFile):''};
    await submitExtraction(payload);
  } catch(error) { toast(error.message,true); }
  finally { button.disabled=false; button.querySelector('span').textContent='Phân tích dữ liệu'; }
}
async function extractFromResults() {
  const rows=state.filtered.filter(row=>row.notify_no||planDisplayCode(row));
  if(!rows.length)return toast('Chưa có mã TBMT hoặc KHLCNT trong kết quả đang lọc.',true);
  const button=$('extractFromResults'); button.disabled=true; button.textContent='Đang lấy mã…';
  try {
    await submitExtraction({job_id:state.jobId,indices:rows.map(row=>row.index),remove_duplicates:$('extractDeduplicate').checked}, 'results');
    if(typeof showView==='function')showView('codes');
    $('extractor').scrollIntoView({behavior:'smooth',block:'start'});
  } catch(error) { toast(error.message,true); }
  finally { button.disabled=false; button.textContent=`Lấy ${rows.length} mã đang lọc`; }
}
function renderExtraction() {
  $('exportExtracted').disabled=!state.extractionId || !state.extracted.length || state.extractionStatus!=='done';
  const rows=state.extracted; $('extractCount').textContent=`${rows.length} mã`; $('extractEmpty').classList.toggle('hidden',rows.length>0); $('extractResult').classList.toggle('hidden',rows.length===0);
  const selected=extractedSelectionIndices().length;
  $('extractSelectAll').checked=rows.length>0&&selected===rows.length;
  $('extractSelectAll').indeterminate=selected>0&&selected<rows.length;
  $('extractSelectionText').textContent=`Đã chọn ${selected}/${rows.length} mã`;
  const selectedIb=extractedSelectionIndices().filter(index=>rows[index]?.code?.startsWith('IB')).length;
  $('downloadExtractedLots').disabled=state.lotsLoading||!selectedIb;
  $('downloadExtractedLots').textContent=state.lotsLoading?'Đang tải Excel…':`Tải Excel phân lô (${selectedIb} TBMT)`;
  $('extractBody').innerHTML=rows.map((row,index)=>{const isPlan=row.code?.startsWith('PL'),type=row.code_type||(isPlan?'KHLCNT':'TBMT'),status=isPlan?(row.lookup_error||'—'):(row.tender_status||row.lookup_error||(state.extractionStatus==='done'?'Chưa xác định':'Đang tra cứu…'));return `<tr><td class="check-col"><input class="extract-check" type="checkbox" data-index="${index}" aria-label="Chọn ${esc(row.code)}" ${state.extractedSelected.has(index)?'checked':''}></td><td>${index+1}</td><td>${esc(type)}</td><td><span class="code">${esc(row.code)}</span></td><td>${esc(row.title||'—')}</td><td>${esc(row.investor_name||'—')}</td><td><span class="status-badge ${statusClass(isPlan?'':row.tender_status)}">${esc(status)}</span></td><td>${esc(row.location||'—')}</td><td>${esc(row.bid_form||'—')}</td></tr>`;}).join('');
  $('extractMore').textContent=state.extractionStatus==='done'?`Hiển thị toàn bộ ${rows.length} mã.`:`Đang tra cứu thông tin: ${state.extractionProcessed}/${rows.length} mã.`;
}
function extractedColumnText(key) {
  return state.extracted.map((row,index)=>{
    if(key==='__stt')return String(index+1);
    if(key==='code_type')return row.code_type||(row.code?.startsWith('PL')?'KHLCNT':'TBMT');
    if(key==='tender_status')return row.code?.startsWith('PL')?(row.lookup_error||'—'):(row.tender_status||row.lookup_error||(state.extractionStatus==='done'?'Chưa xác định':'Đang tra cứu…'));
    return String(row[key]|| (['location','bid_form','title','investor_name'].includes(key)?'—':''));
  }).map(value=>value.replace(/[\t\r\n]+/g,' ')).join('\n');
}
async function copyExtractedColumn(key, label) {
  if(!state.extracted.length)return toast('Chưa có dữ liệu trong cột để sao chép.',true);
  await copyText(extractedColumnText(key));
  toast(`Đã sao chép cột ${label} · ${state.extracted.length} dòng.`);
}
async function exportExtraction() {
  if(!state.extractionId||!state.extracted.length||state.extractionStatus!=='done')return toast('Hãy chờ tra cứu xong danh sách mã trước khi xuất.',true);
  const id=state.extractionId;
  const task=typeof beginDownloadTask==='function'?beginDownloadTask('Danh sách mã TBMT / KHLCNT','Danh sách mã'):null;
  try {
    const response=await api('/api/export-codes',{method:'POST',body:JSON.stringify({extraction_id:id,expected_count:state.extracted.length})});
    const blob=await response.blob();
    if(state.extractionId!==id)return toast('Danh sách mã đã thay đổi. Hãy xuất lại danh sách hiện tại.',true);
    await saveBlob(blob,responseFilename(response,'Danh_sach_ma_TBMT_KHLCNT.xlsx'));
    if(typeof finishDownloadTask==='function')finishDownloadTask(task);
  } catch(error) { if(typeof failDownloadTask==='function')failDownloadTask(task,error); toast(error.message,true); }
}

$('searchForm').addEventListener('submit',startSearch); document.querySelectorAll('input[name="mode"]').forEach(el=>el.addEventListener('change',syncMode)); $('resetSearch').addEventListener('click',resetSearch);
const applyQuickFilterDebounced=debounce(applyView);
$('quickFilter').addEventListener('input',()=>state.rows.length>200?applyQuickFilterDebounced():applyView()); $('sortBy').addEventListener('change',applyView);
['viewStatus','viewLocation','viewDeadline'].forEach(id=>$(id).addEventListener('change',applyView));
$('clearViewFilters').addEventListener('click',clearViewFilters);
$('savePreset').addEventListener('click',()=>updatePreset('save'));
$('deletePreset').addEventListener('click',()=>updatePreset('delete'));
$('loadPreset').addEventListener('click',applyPreset);
$('savedPresets').addEventListener('change',syncPresetControls);
for(const [id,action] of [['pinPreset','pin'],['watchPreset','watch'],['renamePreset','rename']])$(id).addEventListener('click',()=>changePreset(action));
document.querySelectorAll('[data-date-range]').forEach(button=>button.addEventListener('click',()=>setDateRange(button.dataset.dateRange)));
$('densityToggle').addEventListener('click',()=>{const compact=$('results').classList.toggle('compact');$('densityToggle').setAttribute('aria-pressed',String(compact));$('densityToggle').textContent=compact?'Bảng thoáng':'Bảng gọn';});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&$('commandPalette').classList.contains('hidden'))closeDetail();
});
 $('resultBody').addEventListener('change',e=>{if(e.target.classList.contains('row-check'))toggleRow(Number(e.target.dataset.index),e.target.checked);}); $('resultBody').addEventListener('click',e=>{const check=e.target.closest('[data-check-lot]');if(check){checkLot(Number(check.dataset.checkLot));return;}const btn=e.target.closest('[data-detail]');if(btn)openDetail(Number(btn.dataset.detail));});
const resultHeader=$('results').querySelector('thead');
resultHeader.querySelectorAll('th[data-copy]').forEach(th=>{th.tabIndex=0;th.setAttribute('aria-keyshortcuts','Enter Space');});
resultHeader.addEventListener('click',e=>{const th=e.target.closest('th[data-copy]');if(th&&!e.target.closest('.column-grip'))void activateResultHeader(th,e.shiftKey);});
resultHeader.addEventListener('keydown',e=>{if(e.key!=='Enter'&&e.key!==' ')return;const th=e.target.closest('th[data-copy]');if(th){e.preventDefault();void activateResultHeader(th,e.shiftKey);}});
$('selectAll').addEventListener('change',e=>{const size=Number($('pageSize').value)||50;state.filtered.slice((state.page-1)*size,state.page*size).forEach(r=>e.target.checked?state.selected.add(r.index):state.selected.delete(r.index));render();});
$('chooseFolder').addEventListener('click',chooseFolder); $('exportExcel').addEventListener('click',()=>download('/api/export',state.selected.size>0,'Ket_qua.xlsx')); $('downloadLots').addEventListener('click',()=>download('/api/lots',true,'Phan_lo.xlsx'));
$('copyCodes').addEventListener('click',async()=>{const chosen=state.selected.size?state.rows.filter(r=>state.selected.has(r.index)):state.filtered;const codes=[...new Set(chosen.map(r=>r.notify_no||planDisplayCode(r)).filter(Boolean))];if(!codes.length)return toast('Chưa có mã để sao chép.',true);await copyText(codes.join('\n'));toast(`Đã sao chép ${codes.length} mã.`);});
$('closeDrawer').addEventListener('click',closeDetail); $('drawerBackdrop').addEventListener('click',closeDetail); document.querySelectorAll('[data-scroll]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-scroll]').forEach(item=>item.classList.toggle('active',item===b));$(b.dataset.scroll).scrollIntoView({behavior:'smooth'});}));
$('dropZone').addEventListener('click',()=>$('extractFile').click()); $('extractFile').addEventListener('change',e=>setExtractFile(e.target.files[0]));
['dragenter','dragover'].forEach(name=>$('dropZone').addEventListener(name,e=>{e.preventDefault();$('dropZone').classList.add('dragging');})); ['dragleave','drop'].forEach(name=>$('dropZone').addEventListener(name,e=>{e.preventDefault();$('dropZone').classList.remove('dragging');})); $('dropZone').addEventListener('drop',e=>setExtractFile(e.dataTransfer.files[0]));
$('runExtract').addEventListener('click',runExtraction); $('extractFromResults').addEventListener('click',extractFromResults); $('copyExtracted').addEventListener('click',async()=>{if(!state.extracted.length)return toast('Chưa có mã để sao chép.',true);await copyText(state.extracted.map(row=>row.code).join('\n'));toast(`Đã sao chép ${state.extracted.length} mã TBMT/KHLCNT.`);}); $('exportExtracted').addEventListener('click',exportExtraction);
$('extractor').querySelector('thead').addEventListener('click',e=>{const th=e.target.closest('th[data-copy]');if(th)copyExtractedColumn(th.dataset.copy,th.textContent.trim());});
$('extractSelectAll').addEventListener('change',e=>selectAllExtracted(e.target.checked));
$('extractBody').addEventListener('change',e=>{if(!e.target.classList.contains('extract-check'))return;const index=Number(e.target.dataset.index);e.target.checked?state.extractedSelected.add(index):state.extractedSelected.delete(index);renderExtraction();});
$('downloadExtractedLots').addEventListener('click',downloadExtractedLots);
$('saveAllLotFiles').addEventListener('click',retryLotFiles);
$('chooseLotFolder').addEventListener('click',chooseFolder);
$('extractText').addEventListener('input',clearExtraction); $('extractDeduplicate').addEventListener('change',clearExtraction);
$('recentList').addEventListener('click',e=>{const b=e.target.closest('[data-recent]');if(b)loadRecent(Number(b.dataset.recent));});
$('themeToggle').addEventListener('click',()=>{document.body.classList.toggle('dark');writeLocal('msc_theme',document.body.classList.contains('dark')?'dark':'light');});
$('stopServer').addEventListener('click',async()=>{try{await api('/api/shutdown',{method:'POST',body:'{}'});document.body.innerHTML='<main style="display:grid;place-content:center;height:100vh;text-align:center;font-family:Segoe UI"><h1>Đã dừng MuaSamCong Web</h1><p>Bạn có thể đóng thẻ này.</p></main>';}catch(error){toast(error.message,true);}});
if(readLocal('msc_theme','light')==='dark')document.body.classList.add('dark'); initDates(); syncMode(); renderRecent(); render(); renderExtraction(); loadPresets();
// Reevaluate the deadline window even if the user leaves the desk open.
setInterval(()=>{if(!state.loading&&state.rows.length){if($('viewDeadline').value)applyView();else render();}},60000);
