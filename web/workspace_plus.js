/* Tender workflow, change history, detail view, command palette and download archive. */
state.downloadArchive=[];
state.downloadPending=[];
state.downloadFetchState='unfetched';
state.paletteItems=[];
state.paletteIndex=0;

function displayTime(value) {
  if(!value)return 'Chưa cập nhật';
  const date=new Date(value);
  return Number.isNaN(date.getTime())?'Chưa cập nhật':date.toLocaleString('vi-VN',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
}
function trackedItem(code) { return state.watchlist.find(item=>item.code===code); }
function statusLine(item) {
  if(item.fetch_state==='error')return `<span class="data-error">Không lấy được dữ liệu: ${esc(item.fetch_error||'Lỗi kết nối')}</span>`;
  if(item.fetch_state==='ok')return `Cập nhật lần cuối: ${displayTime(item.last_checked)}`;
  return 'Chưa fetch dữ liệu · Bấm Thử lại để kiểm tra e-GP';
}
function renderTrackingWorkspace() {
  const terms=normalizeSearch($('trackingSearch').value).trim().split(/\s+/).filter(Boolean);
  const status=$('trackingStatus').value, priority=$('trackingPriority').value, updates=$('trackingOnlyUpdates').checked;
  const items=state.watchlist.filter(item=>{
    if(status&&item.workflow_status!==status)return false;
    if(priority&&item.priority!==priority)return false;
    if(updates&&!item.has_update)return false;
    const text=normalizeSearch([item.code,item.name,item.investor,item.note,...(item.tags||[])].join(' '));
    return terms.every(term=>text.includes(term));
  }).sort((a,b)=>Number(Boolean(b.pinned))-Number(Boolean(a.pinned))||
    ({'Khẩn cấp':4,Cao:3,'Trung bình':2,Thấp:1}[b.priority]||0)-({'Khẩn cấp':4,Cao:3,'Trung bình':2,Thấp:1}[a.priority]||0));
  $('trackingCount').textContent=`${state.watchlist.length} gói`;
  $('trackingList').innerHTML=items.length?items.map(item=>{
    const snapshot=item.snapshot||{}, code=esc(item.code), changes=item.changes||[];
    const latest=changes[0];
    const updateBadge=item.has_update?'<span class="update-badge"><i data-lucide="circle-alert" aria-hidden="true"></i> Có cập nhật mới</span>':'';
    return `<article class="tracking-work-card" data-track-code="${code}"><div class="tracking-work-top"><div><div class="tracking-work-meta"><span class="code">${code}</span>${item.pinned?'<span class="pin-badge"><i data-lucide="pin" aria-hidden="true"></i> Đã ghim</span>':''}${updateBadge}</div><button class="tracking-title" data-tracking-open="${code}">${esc(item.name||code)}</button><p>${esc(item.investor||'Chưa có chủ đầu tư')} · ${esc(snapshot.procuring_entity_name||'Chưa có bên mời thầu')}</p></div><div class="tracking-work-actions"><button class="btn ghost" data-track-pin="${code}"><i data-lucide="pin" aria-hidden="true"></i> ${item.pinned?'Bỏ ghim':'Ghim'}</button><button class="btn ghost ${state.refreshingTrackedCode===item.code?'is-loading':''}" data-track-refresh="${code}" ${state.refreshingTrackedCode===item.code?'disabled aria-busy="true"':''}>${state.refreshingTrackedCode===item.code?'Đang cập nhật…':'Thử lại'}</button><button class="btn ghost" data-unwatch="${code}">Bỏ theo dõi</button></div></div>
      <div class="tracking-work-grid"><div><small>Đóng thầu</small><strong>${esc(item.deadline||'Chưa có dữ liệu')}</strong><span>${remainingTime(item.deadline)}</span></div><div><small>Trạng thái e-GP</small><strong>${esc(snapshot.tender_status||'Chưa có dữ liệu')}</strong></div><label><small>Trạng thái xử lý</small><select data-track-status="${code}">${['Mới','Đang xem','Quan tâm','Đang xử lý','Hoàn tất','Bỏ qua'].map(value=>`<option ${item.workflow_status===value?'selected':''}>${value}</option>`).join('')}</select></label><label><small>Ưu tiên</small><select data-track-priority="${code}">${['Thấp','Trung bình','Cao','Khẩn cấp'].map(value=>`<option ${item.priority===value?'selected':''}>${value}</option>`).join('')}</select></label></div>
      <div class="tracking-work-note"><label>Ghi chú<textarea data-track-note="${code}" placeholder="Thêm ghi chú cho nhóm…">${esc(item.note||'')}</textarea></label><div><small>Tag</small><div class="tag-list">${(item.tags||[]).map(tag=>`<span class="tag-chip">${esc(tag)} <button data-track-remove-tag="${code}" data-tag="${esc(tag)}" title="Xóa tag">×</button></span>`).join('')}</div><input data-track-tag-input="${code}" maxlength="30" placeholder="Thêm tag"><button class="btn ghost" data-track-add-tag="${code}">Thêm</button></div></div>
      <div class="tracking-work-bottom"><span class="data-status">${statusLine(item)}</span>${item.has_update?`<button class="text-btn" data-track-read="${code}">Đánh dấu đã xem</button>`:''}</div>${latest?`<details class="change-log"><summary>Lịch sử thay đổi · ${changes.length} mục</summary>${changes.map(change=>`<div><time>${displayTime(change.time)}</time><strong>${esc(change.label||change.field)}</strong><span>${esc(change.from||'Chưa có dữ liệu')} → ${esc(change.to||'Chưa có dữ liệu')}</span></div>`).join('')}</details>`:''}</article>`;
  }).join(''):'<p class="empty-inline">'+(state.watchlist.length?'Không có gói khớp bộ lọc.':'Chưa có gói nào được theo dõi. Tới Tra cứu và bấm Theo dõi ở gói cần lưu.')+'</p>';
}
renderTrackingList=renderTrackingWorkspace;

async function editTracked(code, patch) {
  try { state.watchlist=(await (await api('/api/watchlist',{method:'POST',body:JSON.stringify({action:'edit',code,...patch})})).json()).items||[];renderTrackingList();renderStats(); }
  catch(error){toast(error.message,true);}
}
async function refreshTracked(code) {
  const item=trackedItem(code);if(!item)return;
  if(state.refreshingTrackedCode===code)return;
  state.refreshingTrackedCode=code;renderTrackingList();
  $('trackingDataStatus').textContent=`Đang kiểm tra ${code} trên e-GP…`;
  try {
    const result=await (await api('/api/refresh-watch',{method:'POST',body:JSON.stringify({code})})).json();
    state.watchlist=result.items||[];
    const row=state.rows.find(value=>watchedCode(value)===code);
    if(row&&result.row){Object.assign(row,{...result.row,index:row.index});rowSearchCache.delete(row);}
    render();renderTrackingList();
    $('trackingDataStatus').textContent=`Cập nhật lần cuối: ${displayTime(new Date().toISOString())}`;
    if(state.detailRow&&watchedCode(state.detailRow)===code)openDetailRow(row||trackedRow(trackedItem(code)));
    toast(`Đã kiểm tra ${code}.`);
  } catch(error) { await loadWatchlist();$('trackingDataStatus').innerHTML=`<span class="data-error">Không lấy được dữ liệu: ${esc(error.message)}</span> · <button type="button" data-retry-tracking="${esc(code)}">Thử lại</button>`; }
  finally {state.refreshingTrackedCode=null;renderTrackingList();}
}
async function syncWatchlistAfterSearch() {
  const matched=state.rows.filter(row=>trackedItem(watchedCode(row))).map(row=>({code:watchedCode(row),...row}));
  if(!matched.length)return;
  try { state.watchlist=(await (await api('/api/watchlist',{method:'POST',body:JSON.stringify({action:'sync',rows:matched})})).json()).items||[];renderTrackingList();render(); }
  catch(error) { $('trackingDataStatus').innerHTML=`<span class="data-error">Không đồng bộ được gói theo dõi: ${esc(error.message)}</span> · <button type="button" data-retry-tracking="all">Thử lại</button>`; }
}
function trackedRow(item) {
  const snapshot=item?.snapshot||{};
  return {...snapshot,notify_no:item?.code?.startsWith('IB')?item.code:'',plan_no:item?.code?.startsWith('PL')?item.code.slice(2):snapshot.plan_no||'',source_url:item?.url||snapshot.source_url||'',package_name:item?.name||snapshot.package_name||'',investor_name:item?.investor||snapshot.investor_name||'',bid_close_date:item?.deadline||snapshot.bid_close_date||'',index:-1};
}

function detailField(label,value) { return `<div class="detail-item"><span>${label}</span><strong>${esc(value||'Không có dữ liệu từ nguồn')}</strong></div>`; }
function openDetailRow(row) {
  if(!row)return;
  state.detailRow=row;
  const code=watchedCode(row), item=trackedItem(code), source=officialDetailUrl(row)||item?.url||'';
  $('drawerCode').textContent=code||'Gói thầu';
  $('detailDataStatus').innerHTML=item?statusLine(item):state.lastFetchedAt?`Cập nhật lần cuối: ${displayTime(state.lastFetchedAt)}`:'Chưa fetch lại gói này';
  $('detailToolbar').innerHTML=`<button class="btn ghost" data-detail-action="watch"><i data-lucide="star" aria-hidden="true"></i> ${item?'Đang theo dõi':'Theo dõi'}</button>${row.notify_no?'<button class="btn ghost" data-detail-action="profile">Mở hồ sơ gói ↗</button>':''}<button class="btn ghost" data-detail-action="copy"><i data-lucide="copy" aria-hidden="true"></i> Sao chép mã</button>${source?`<a class="btn ghost" href="${esc(source)}" target="_blank" rel="noopener noreferrer"><i data-lucide="external-link" aria-hidden="true"></i> Mở nguồn</a>`:''}<button class="btn ghost" data-detail-action="refresh"><i data-lucide="refresh-cw" aria-hidden="true"></i> Cập nhật</button><button class="btn ghost" data-detail-action="export"><i data-lucide="file-spreadsheet" aria-hidden="true"></i> Xuất Excel</button><button class="btn ghost" data-detail-action="ai"><i data-lucide="file-search" aria-hidden="true"></i> AI Hồ sơ</button>`;
  const timeline=[['Đăng tải',row.public_date],['Hạn đóng thầu',row.bid_close_date],['Công bố kết quả',row.winner?row.decision_date:null]].filter(([,date])=>date);
  $('drawerBody').innerHTML=`<section class="detail-section"><h3>Thông tin chung</h3><div class="detail-grid">${detailField('Mã TBMT',row.notify_no)}${detailField('KHLCNT',planDisplayCode(row))}${detailField('Tên gói',row.package_name||row.plan_name)}${detailField('Chủ đầu tư',row.investor_name)}${detailField('Bên mời thầu',row.procuring_entity_name)}${detailField('Giá gói thầu',row.package_price)}${detailField('Ngày đăng',row.public_date)}${detailField('Đóng thầu',row.bid_close_date)}${detailField('Địa điểm',row.location)}${detailField('Trạng thái',row.tender_status)}</div></section>
    <section class="detail-section"><h3>Timeline theo nguồn</h3>${timeline.length?`<div class="detail-timeline">${timeline.map(([label,date],index)=>`<div class="reached"><span>${index+1}</span><strong>${label}</strong><small>${esc(date)}</small></div>`).join('')}</div>`:'<p class="detail-hint">Nguồn chưa cung cấp mốc thời gian.</p>'}<p class="detail-hint">Chỉ hiện mốc có ngày trong dữ liệu đã lấy.</p></section>
    <section class="detail-section"><h3>Kết quả</h3>${detailField('Nhà thầu trúng',row.winner)}${detailField('Giá trúng',row.winning_price)}<p class="detail-hint">Dữ liệu KQLCNT chỉ hiện khi e-GP đã công bố và truy vấn tải được chi tiết.</p></section>
    ${row.notify_no?'':`<section class="detail-section"><h3>Phân lô</h3><p>${esc(lotFileLabel(row))}</p><button class="btn lot-btn" data-detail-action="lots" ${Number.isInteger(row.index)&&row.index>=0&&state.jobId?'':'disabled'}>Tải Excel phân lô của gói</button></section>`}
    ${item?.changes?.length?`<section class="detail-section"><h3>Lịch sử thay đổi</h3>${item.changes.slice(0,10).map(change=>`<p class="detail-change"><strong>${esc(change.label||change.field)}</strong>: ${esc(change.from||'Chưa có dữ liệu')} → ${esc(change.to||'Chưa có dữ liệu')} <small>${displayTime(change.time)}</small></p>`).join('')}</section>`:''}
    <section class="detail-section"><h3>AI Hồ sơ</h3><p id="detailAiDocuments">Đang tải tài liệu liên kết…</p><button class="btn ghost" data-detail-action="ai"><i data-lucide="upload" aria-hidden="true"></i> Mở AI Hồ sơ / tải HSMT</button></section>`;
  if(typeof renderAiTenderDocuments==='function')void renderAiTenderDocuments(code);
  $('detailDrawer').classList.add('open');$('drawerBackdrop').classList.add('open');$('detailDrawer').setAttribute('aria-hidden','false');
}
openDetail=function(index){const row=state.rows.find(item=>item.index===index);if(row)openDetailRow(row);};

function renderHistoryWorkspace() {
  const list=recentQueries().map((item,index)=>({item,index})).sort((a,b)=>Number(Boolean(b.item.pinned))-Number(Boolean(a.item.pinned))||new Date(b.item.time)-new Date(a.item.time));
  $('historyList').innerHTML=list.length?list.map(({item,index})=>`<article class="history-work-item"><div><div><strong>${esc(item.name||item.keyword||'Tất cả TBMT')}</strong>${item.pinned?'<span class="pin-badge"><i data-lucide="pin" aria-hidden="true"></i> Đã ghim</span>':''}</div><small>${esc(item.mode||'TBMT')} · ${esc(item.date_from||'—')} → ${esc(item.date_to||'—')} · ${item.result_count===null||item.result_count===undefined?'Chưa có kết quả':`${Number(item.result_count).toLocaleString('vi-VN')} kết quả`}</small><small>Cập nhật lần cuối: ${displayTime(item.time)}</small><div class="history-rename hidden" data-history-editor="${esc(item.id||'')}"><input maxlength="80" value="${esc(item.name||item.keyword||'')}"><button class="btn ghost" data-history-save="${esc(item.id||'')}">Lưu tên</button></div></div><div class="history-actions"><button class="btn ghost" data-rerun="${index}">Chạy lại</button><button class="btn ghost" data-history-pin="${esc(item.id||'')}">${item.pinned?'Bỏ ghim':'Ghim'}</button><button class="btn ghost" data-history-rename="${esc(item.id||'')}">Đổi tên</button><button class="btn ghost" data-history-delete="${esc(item.id||'')}">Xóa</button></div></article>`).join(''):'<p class="empty-inline">Chưa có truy vấn nào. Lịch sử sẽ được lưu sau khi tra cứu.</p>';
}
renderHistoryList=renderHistoryWorkspace;
async function changeHistory(action,id,extra={}) {
  try {state.history=(await (await api('/api/history',{method:'POST',body:JSON.stringify({action,id,...extra})})).json()).items||[];renderRecent();}
  catch(error){toast(error.message,true);}
}
async function completeHistorySearch(params,count) {
  if(state.historySavePromise)await state.historySavePromise.catch(()=>{});
  try { state.history=(await (await api('/api/history',{method:'POST',body:JSON.stringify({action:'complete',params,result_count:count})})).json()).items||[];renderRecent(); }
  catch { /* Query results remain usable if history cannot be updated. */ }
}

function beginDownloadTask(name,kind) {
  const id=`pending-${Date.now()}-${Math.random()}`;
  state.downloadPending.unshift({id,name,kind,status:'Đang xử lý',time:new Date().toISOString(),size:0});
  renderDownloadLibrary();return id;
}
function finishDownloadTask(id) {
  state.downloadPending=state.downloadPending.filter(item=>item.id!==id);
  void loadDownloadArchive(true);
}
function failDownloadTask(id,error) {
  const item=state.downloadPending.find(entry=>entry.id===id);
  if(item){item.status='Lỗi';item.error=error.message;void api('/api/downloads',{method:'POST',body:JSON.stringify({action:'error',name:item.name,kind:item.kind,error:item.error})}).then(()=>{state.downloadPending=state.downloadPending.filter(entry=>entry.id!==id);return loadDownloadArchive(true);}).catch(()=>renderDownloadLibrary());}
  renderDownloadLibrary();
}
async function loadDownloadArchive(force=false) {
  if(state.downloadLoadPromise)return state.downloadLoadPromise;
  if(!force&&state.downloadFetchState==='ok'&&Date.now()-(state.downloadLoadedAt||0)<30000){renderDownloadLibrary();return;}
  state.downloadFetchState='loading';$('downloadsDataStatus').textContent='Đang tải danh sách file…';
  $('refreshDownloads').disabled=true;$('refreshDownloads').classList.add('is-loading');
  state.downloadLoadPromise=(async()=>{
    try {state.downloadArchive=(await (await api('/api/downloads')).json()).items||[];state.downloadFetchState='ok';state.downloadLoadedAt=Date.now();$('downloadsDataStatus').textContent=`Cập nhật lần cuối: ${displayTime(state.downloadLoadedAt)} · ${state.downloadArchive.length} mục`;renderDownloadLibrary();}
    catch(error){state.downloadFetchState='error';$('downloadsDataStatus').innerHTML=`<span class="data-error">Không lấy được dữ liệu: ${esc(error.message)}</span> · <button data-retry-downloads>Thử lại</button>`;renderDownloadLibrary();}
  })();
  try {return await state.downloadLoadPromise;} finally {state.downloadLoadPromise=null;$('refreshDownloads').disabled=false;$('refreshDownloads').classList.remove('is-loading');}
}
function renderDownloadWorkspace() {
  const entries=[...state.downloadPending,...state.downloadArchive];
  $('downloadLibrary').innerHTML=entries.length?entries.map(item=>`<article class="download-work-item"><div class="download-icon"><i data-lucide="file-spreadsheet" aria-hidden="true"></i></div><div class="download-info"><strong>${esc(item.name)}</strong><small>${esc(item.kind||'Excel')} · ${displayTime(item.time)}${item.size?` · ${(item.size/1024).toFixed(1)} KB`:''}</small>${item.error?`<small class="data-error">${esc(item.error)}</small>`:''}</div><span class="download-state ${item.status==='Lỗi'?'error':item.status==='Đang xử lý'?'busy':'complete'}">${esc(item.status)}</span>${item.url?`<a class="btn ghost" href="${esc(item.url)}" download="${esc(item.name)}"><i data-lucide="download" aria-hidden="true"></i> Tải lại</a>`:item.status==='Lỗi'?`<button class="btn ghost" data-download-retry="${esc(item.kind||'Excel')}">Thử lại</button>`:''}</article>`).join(''):'<p class="empty-inline">Chưa có file nào. Xuất Excel từ Tra cứu hoặc Danh sách mã để bắt đầu.</p>';
}
renderDownloadLibrary=renderDownloadWorkspace;

const paletteCommands=[
  ['Tổng quan','Mở Dashboard',()=>showView('overview')],['Tra cứu','Mở Tra cứu',()=>showView('search')],
  ['Theo dõi','Mở Theo dõi',()=>showView('tracking')],['Lịch sử','Mở lịch sử',()=>showView('history')],
  ['Phân tích','Mở Phân tích',()=>showView('analysis')],['AI Hồ sơ','Mở AI Hồ sơ',()=>showView('ai')],
  ['Upload hồ sơ','Tải hồ sơ đấu thầu',()=>{showView('ai');$('aiFileInput').click();}],
  ['Tóm tắt tài liệu','Tóm tắt tài liệu đang chọn',()=>{showView('ai');if(typeof chooseAiTab==='function')chooseAiTab('summary');}],
  ['Trích danh mục','Trích danh mục tài liệu',()=>{showView('ai');if(typeof chooseAiTab==='function')chooseAiTab('catalog');}],
  ['Tải xuống','Mở Download Center',()=>showView('downloads')],['Xuất Excel','Xuất Excel kết quả',()=>download('/api/export',false,'Ket_qua.xlsx')],
  ['Refresh','Refresh dữ liệu',()=>{showView('search');void startSearch(undefined,true);}],['Danh sách mã','Mở Danh sách mã',()=>showView('codes')]
];
function renderPalette() {
  const query=$('commandInput').value.trim(), q=normalizeSearch(query);
  const commands=paletteCommands.filter(([name,label])=>!q||normalizeSearch(name+' '+label).includes(q)).map(([,label,run])=>({label,kind:'Lệnh',run}));
  const rows=state.rows.filter(row=>normalizeSearch([watchedCode(row),row.package_name,row.plan_name,row.investor_name,row.procuring_entity_name].join(' ')).includes(q)).slice(0,8).map(row=>({label:`${watchedCode(row)} · ${row.package_name||row.plan_name||'Gói thầu'}`,kind:'Kết quả đang tải',run:()=>openDetailRow(row)}));
  const watched=state.watchlist.filter(item=>!state.rows.some(row=>watchedCode(row)===item.code)&&normalizeSearch([item.code,item.name,item.investor].join(' ')).includes(q)).slice(0,5).map(item=>({label:`${item.code} · ${item.name||'Gói theo dõi'}`,kind:'Đang theo dõi',run:()=>openDetailRow(trackedRow(item))}));
  const recent=!q?(state.history||[]).slice(0,4).map(item=>({label:item.name||item.keyword||'Truy vấn gần đây',kind:'Gần đây',run:()=>{if(item.mode==='Kho dữ liệu'&&typeof restoreLocalSearch==='function')restoreLocalSearch(item);else{restoreQuery(item);showView('search');void startSearch();}}})):[];
  const saved=!q?(state.presets||[]).slice(0,4).map(item=>({label:item.name,kind:'Đã lưu',run:()=>{if(item.params?.mode==='Kho dữ liệu'&&typeof restoreLocalSearch==='function')restoreLocalSearch(item.params);else{restoreQuery(item.params);showView('search');void startSearch();}}})):[];
  const search=query?[{label:`Tra cứu “${query}” trên e-GP`,kind:'Tra cứu mới',run:()=>{$('keyword').value=query;showView('search');void startSearch();}}]:[];
  state.paletteItems=[...commands,...(state.serverSuggestions||[]),...rows,...watched,...recent,...saved,...search].slice(0,20);
  state.paletteIndex=Math.min(state.paletteIndex,state.paletteItems.length-1);
  $('commandList').innerHTML=state.paletteItems.length?state.paletteItems.map((item,index)=>`<button class="command-item ${index===state.paletteIndex?'active':''}" data-command-index="${index}"><span>${esc(item.label)}</span><small>${item.kind}</small></button>`).join(''):'<p class="empty-inline">Không có lệnh hoặc mã phù hợp.</p>';
}
let suggestionTimer, suggestionController;
function loadPaletteSuggestions() {
  clearTimeout(suggestionTimer);
  suggestionController?.abort();
  state.serverSuggestions=[];
  const query=$('commandInput').value.trim();
  if(!query){renderPalette();return;}
  suggestionTimer=setTimeout(async()=>{
    const controller=new AbortController();suggestionController=controller;
    try {
      const response=await fetch('/api/intelligence/suggest?q='+encodeURIComponent(query),{signal:controller.signal,credentials:'same-origin'});
      if(!response.ok)throw new Error('Không lấy được gợi ý');
      const data=await response.json();
      if(controller.signal.aborted||$('commandInput').value.trim()!==query)return;
      state.serverSuggestions=(data.items||[]).map(item=>({label:`${item.code} · ${item.name||'Chưa có tên'}`,kind:{tender:'TBMT',plan:'KHLCNT',investor:'Chủ đầu tư',procurer:'Bên mời thầu',contractor:'Nhà thầu'}[item.kind]||item.kind,
        run:()=>intelNavigate(item.kind==='tender'?'/app/tenders/'+encodeURIComponent(item.code):item.kind==='plan'?'/app/plans/'+encodeURIComponent(item.code):'/app/entities/'+encodeURIComponent(item.kind)+'/'+encodeURIComponent(item.code))}));
      renderPalette();
    } catch(error){if(error.name!=='AbortError'){state.serverSuggestions=[];renderPalette();}}
  },200);
}
function openPalette(initial='') {$('commandPalette').classList.remove('hidden');$('commandInput').value=initial;state.paletteIndex=0;renderPalette();loadPaletteSuggestions();$('commandInput').focus();}
function closePalette() {clearTimeout(suggestionTimer);suggestionController?.abort();$('commandPalette').classList.add('hidden');}
function runPalette(index) {const item=state.paletteItems[index];if(item){closePalette();item.run();}}

/* Delegated UI events keep cards stable while notes are edited. */
$('trackingSearch').addEventListener('input',renderTrackingList);
for(const id of ['trackingStatus','trackingPriority','trackingOnlyUpdates'])$(id).addEventListener('change',renderTrackingList);
$('trackingList').addEventListener('change',event=>{const status=event.target.closest('[data-track-status]'),priority=event.target.closest('[data-track-priority]');if(status)void editTracked(status.dataset.trackStatus,{workflow_status:status.value});if(priority)void editTracked(priority.dataset.trackPriority,{priority:priority.value});});
$('trackingList').addEventListener('focusout',event=>{const note=event.target.closest('[data-track-note]');if(note&&note.value!==trackedItem(note.dataset.trackNote)?.note)void editTracked(note.dataset.trackNote,{note:note.value});});
$('trackingList').addEventListener('click',event=>{
  const target=event.target.closest('[data-track-pin],[data-track-refresh],[data-track-read],[data-track-add-tag],[data-track-remove-tag],[data-tracking-open],[data-unwatch]');if(!target)return;
  if(target.dataset.unwatch){const item=trackedItem(target.dataset.unwatch);if(item)void toggleWatch(trackedRow(item));return;}
  if(target.dataset.trackPin){const item=trackedItem(target.dataset.trackPin);void editTracked(item.code,{pinned:!item.pinned});}
  if(target.dataset.trackRefresh)void refreshTracked(target.dataset.trackRefresh);
  if(target.dataset.trackRead)void api('/api/watchlist',{method:'POST',body:JSON.stringify({action:'mark-read',code:target.dataset.trackRead})}).then(response=>response.json()).then(data=>{state.watchlist=data.items||[];renderTrackingList();}).catch(error=>toast(error.message,true));
  if(target.dataset.trackAddTag){const code=target.dataset.trackAddTag,item=trackedItem(code),input=$('trackingList').querySelector(`[data-track-tag-input="${code}"]`),tag=input?.value.trim();if(tag)void editTracked(code,{tags:[...(item.tags||[]),tag]});}
  if(target.dataset.trackRemoveTag){const code=target.dataset.trackRemoveTag,item=trackedItem(code);void editTracked(code,{tags:(item.tags||[]).filter(tag=>tag!==target.dataset.tag)});}
  if(target.dataset.trackingOpen)openDetailRow(trackedRow(trackedItem(target.dataset.trackingOpen)));
});
$('trackingDataStatus').addEventListener('click',event=>{const button=event.target.closest('[data-retry-tracking]');if(button){if(button.dataset.retryTracking==='all')void syncWatchlistAfterSearch();else if(button.dataset.retryTracking==='reload')void loadWatchlist();else void refreshTracked(button.dataset.retryTracking);}});
$('historyList').addEventListener('click',event=>{const pin=event.target.closest('[data-history-pin]'),rename=event.target.closest('[data-history-rename]'),save=event.target.closest('[data-history-save]'),remove=event.target.closest('[data-history-delete]');if(pin){const item=recentQueries().find(entry=>entry.id===pin.dataset.historyPin);if(item)void changeHistory('pin',item.id,{pinned:!item.pinned});}if(rename){const editor=$('historyList').querySelector(`[data-history-editor="${rename.dataset.historyRename}"]`);editor?.classList.remove('hidden');editor?.querySelector('input')?.focus();}if(save){const editor=$('historyList').querySelector(`[data-history-editor="${save.dataset.historySave}"]`);void changeHistory('rename',save.dataset.historySave,{name:editor?.querySelector('input')?.value||''});}if(remove)void changeHistory('delete',remove.dataset.historyDelete);});
$('historyDataStatus').addEventListener('click',event=>{if(event.target.closest('[data-retry-history]'))void loadHistory();});
$('detailToolbar').addEventListener('click',event=>{const button=event.target.closest('[data-detail-action]');if(!button||!state.detailRow)return;const row=state.detailRow,code=watchedCode(row);switch(button.dataset.detailAction){case 'watch':void toggleWatch(row).then(()=>openDetailRow(row));break;case 'profile':closeDetail();if(typeof intelNavigate==='function')intelNavigate('/app/tenders/'+encodeURIComponent(code));break;case 'copy':void copyText(code).then(()=>toast(`Đã sao chép ${code}.`));break;case 'refresh':if(trackedItem(code))void refreshTracked(code);else{$('keyword').value=code;closeDetail();showView('search');void startSearch(undefined,true);}break;case 'export':if(state.jobId&&Number.isInteger(row.index)&&row.index>=0)void exportDetailRow(row);else toast('Hãy tra cứu lại mã này để xuất Excel.',true);break;case 'ai':closeDetail();showView('ai');void loadAiWorkspace().then(()=>$('aiTenderCode').value=code);break;}});
$('drawerBody').addEventListener('click',event=>{if(event.target.closest('[data-detail-action="ai"]')&&state.detailRow){const code=watchedCode(state.detailRow);closeDetail();showView('ai');void loadAiWorkspace().then(()=>$('aiTenderCode').value=code);}});
$('drawerBody').addEventListener('click',event=>{const button=event.target.closest('[data-detail-action="lots"]');if(button&&state.detailRow&&state.jobId)void downloadLotSelection({job_id:state.jobId,indices:[state.detailRow.index]},1);});
async function exportDetailRow(row) {const task=beginDownloadTask(`${watchedCode(row)}.xlsx`,'Excel kết quả');try{const response=await api('/api/export',{method:'POST',body:JSON.stringify({job_id:state.jobId,indices:[row.index]})});await saveBlob(await response.blob(),responseFilename(response,`${watchedCode(row)}.xlsx`));finishDownloadTask(task);}catch(error){failDownloadTask(task,error);toast(error.message,true);}}
$('refreshDownloads').addEventListener('click',()=>void loadDownloadArchive(true));
$('downloadsDataStatus').addEventListener('click',event=>{if(event.target.closest('[data-retry-downloads]'))void loadDownloadArchive(true);});
$('downloadLibrary').addEventListener('click',event=>{const button=event.target.closest('[data-download-retry]');if(!button)return;const kind=button.dataset.downloadRetry;if(kind==='Danh sách mã')void exportExtraction();else if(kind==='Excel phân lô'){showView('search');toast('Chọn gói cần tải phân lô rồi bấm Tải Excel phân lô.');}else void download('/api/export',false,'Ket_qua.xlsx');});
$('commandInput').addEventListener('input',()=>{state.paletteIndex=0;renderPalette();loadPaletteSuggestions();});
$('commandInput').addEventListener('keydown',event=>{if(event.key==='ArrowDown'){event.preventDefault();state.paletteIndex=Math.min(state.paletteIndex+1,state.paletteItems.length-1);renderPalette();}if(event.key==='ArrowUp'){event.preventDefault();state.paletteIndex=Math.max(0,state.paletteIndex-1);renderPalette();}if(event.key==='Enter'){event.preventDefault();runPalette(state.paletteIndex);}if(event.key==='Escape'){event.preventDefault();closePalette();}});
$('commandList').addEventListener('click',event=>{const button=event.target.closest('[data-command-index]');if(button)runPalette(Number(button.dataset.commandIndex));});
$('commandPalette').addEventListener('click',event=>{if(event.target===$('commandPalette'))closePalette();});
$('globalSearch').setAttribute('readonly','');
$('globalSearch').addEventListener('click',()=>openPalette());
$('globalSearch').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();event.stopImmediatePropagation();openPalette();}},true);
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();openPalette();}else if(event.key==='Escape'&&!$('commandPalette').classList.contains('hidden'))closePalette();});
$('results').addEventListener('click',event=>{if(event.target.closest('[data-retry-search]'))void startSearch();});

const originalSaveRecent=saveRecent;
saveRecent=function(params){originalSaveRecent(params);state.historySavePromise=api('/api/history',{method:'POST',body:JSON.stringify({params})}).then(response=>response.json()).then(data=>{state.history=data.items||state.history;renderRecent();}).catch(()=>{});};
loadWatchlist=async function(){
  $('trackingDataStatus').textContent='Đang tải danh sách theo dõi…';
  try {state.watchlist=(await (await api('/api/watchlist')).json()).items||[];render();renderTrackingList();$('trackingDataStatus').textContent=state.watchlist.length?`Cập nhật lần cuối: ${displayTime(new Date().toISOString())}`:'Chưa có gói theo dõi.';}
  catch(error){$('trackingDataStatus').innerHTML=`<span class="data-error">Không lấy được dữ liệu: ${esc(error.message)}</span> · <button data-retry-tracking="reload">Thử lại</button>`;}
};
function updateOverviewDataStatus() {
  const status=$('overviewDataStatus');
  if(state.searchState==='loading')status.textContent='Đang tải dữ liệu từ e-GP…';
  else if(state.searchState==='error')status.innerHTML=`<span class="data-error">Không lấy được dữ liệu: ${esc(state.searchError||'Lỗi kết nối')}</span> · <button type="button" data-retry-overview>Thử lại</button>`;
  else if(state.searchState==='ok')status.textContent=`Cập nhật lần cuối: ${displayTime(state.lastFetchedAt)} · ${Number(state.sourceCount||0).toLocaleString('vi-VN')} kết quả`;
  else status.textContent='Chưa fetch dữ liệu · Hãy tra cứu để cập nhật.';
}
const statusBaseRender=render;
render=function(updateAnalysis=false){statusBaseRender(updateAnalysis);updateOverviewDataStatus();};
const statusBaseSetLoading=setLoading;
setLoading=function(active,message=''){statusBaseSetLoading(active,message);updateOverviewDataStatus();};
$('overviewDataStatus').addEventListener('click',event=>{if(event.target.closest('[data-retry-overview]')){showView('search');void startSearch();}});
updateOverviewDataStatus();
void loadDownloadArchive();
