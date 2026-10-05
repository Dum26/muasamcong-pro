/* Workspace navigation and local tender tracking. Core search and export APIs stay unchanged. */
const viewNames={overview:'Tổng quan',search:'Tra cứu',tracking:'Theo dõi',codes:'Danh sách mã',history:'Lịch sử',analysis:'Phân tích truy vấn',bi:'Phân tích BI',automations:'Tự động hóa',intelligence:'Dữ liệu đấu thầu',ai:'AI Hồ sơ',documents:'Tài liệu',downloads:'Tải xuống',settings:'Cài đặt'};
const viewRoutes={overview:'/app',search:'/app/search',tracking:'/app/watchlist',codes:'/app/codes',history:'/app/history',analysis:'/app/analysis',bi:'/app/analytics',automations:'/app/automations',intelligence:'/app/intelligence',ai:'/app/ai',documents:'/app/documents',downloads:'/app/downloads',settings:'/app/settings'};
function viewForLocation(){return Object.keys(viewRoutes).find(view=>viewRoutes[view]===window.location.pathname)||(/^\/app\/documents\//.test(window.location.pathname)?'documents':/^\/app\/(tenders|plans|investors|contractors|procurers)\//.test(window.location.pathname)?'intelligence':/^\/app\/(analytics\/|reports\/|dashboard\/custom)/.test(window.location.pathname)?'bi':'overview');}
function showView(view,updateUrl=true) {
  if(!viewNames[view])view='overview';
  if(updateUrl&&window.location.pathname==='/legacy')window.history.pushState({view},'','/legacy#'+view);
  else if(updateUrl&&window.location.pathname!==viewRoutes[view])window.history.pushState({view},'',viewRoutes[view]);
  document.body.dataset.view=view;
  document.querySelectorAll('[data-section]').forEach(section=>{section.hidden=section.dataset.section!==view&&!(view==='overview'&&section.dataset.section==='analysis');});
  document.querySelectorAll('[data-view]').forEach(button=>button.classList.toggle('active',button.dataset.view===view));
  $('currentViewName').textContent=viewNames[view];
  document.querySelector('.sidebar').classList.remove('mobile-open');
  window.scrollTo({top:0,behavior:'instant'});
  if(view==='tracking')renderTrackingList();
  if(view==='history')renderHistoryList();
  if(view==='downloads')renderDownloadLibrary();
  if(view==='downloads'&&typeof loadDownloadArchive==='function')void loadDownloadArchive();
  if(view==='intelligence'&&typeof loadIntelWorkspace==='function')void loadIntelWorkspace();
  if(view==='bi'&&typeof loadBiWorkspace==='function')void loadBiWorkspace();
  if(view==='automations'&&typeof loadAutomationWorkspace==='function')void loadAutomationWorkspace();
  if(view==='ai'&&typeof loadAiWorkspace==='function')void loadAiWorkspace();
  if(view==='documents'&&typeof loadDocumentCenter==='function')void loadDocumentCenter();
}
function watchedCode(row) { return row.notify_no||planDisplayCode(row); }
async function loadWatchlist() {
  try { state.watchlist=(await (await api('/api/watchlist')).json()).items||[]; renderStats(); render(); }
  catch(error) { toast(`Không đọc được danh sách theo dõi: ${error.message}`,true); }
}
async function loadHistory() {
  const current=state.history;
  $('historyDataStatus').textContent='Đang tải lịch sử truy vấn…';
  try {
    let items=(await (await api('/api/history')).json()).items||[];
    if(state.history===current){state.history=items;renderRecent();$('historyDataStatus').textContent=items.length?`Cập nhật lần cuối: ${new Date().toLocaleString('vi-VN')}`:'Chưa có truy vấn đã lưu.';}
  } catch(error) { if(state.history===current){state.history=[];renderRecent();$('historyDataStatus').innerHTML=`<span class="data-error">Không lấy được dữ liệu: ${esc(error.message)}</span> · <button data-retry-history>Thử lại</button>`;} }
}
async function toggleWatch(row) {
  const code=watchedCode(row), existing=state.watchlist.some(item=>item.code===code);
  if(!code)return;
  try {
    const body={action:existing?'remove':'add',code,name:row.package_name||row.plan_name||'',investor:row.investor_name||'',deadline:row.bid_close_date||'',url:officialDetailUrl(row),row};
    state.watchlist=(await (await api('/api/watchlist',{method:'POST',body:JSON.stringify(body)})).json()).items||[];
    render(); renderTrackingList(); toast(existing?`Đã bỏ theo dõi ${code}.`:`Đã theo dõi ${code}.`);
  } catch(error) { toast(error.message,true); }
}
function remainingTime(value) {
  const hours=(parseViDate(value)-Date.now())/3600000;
  if(!Number.isFinite(hours)||!parseViDate(value))return 'Chưa có thời hạn';
  if(hours<=0)return 'Đã đến hạn';
  return `Còn ${Math.floor(hours/24)} ngày ${Math.floor(hours%24)} giờ`;
}
function renderUpcoming() {
  const rows=state.rows.filter(row=>{const h=deadlineHours(row);return h!==null&&h>0;}).sort((a,b)=>parseViDate(a.bid_close_date)-parseViDate(b.bid_close_date)).slice(0,6);
  $('upcomingDeadlines').innerHTML=rows.length?rows.map(row=>{
    const hours=deadlineHours(row), code=watchedCode(row);
    return `<article class="deadline-item"><div><button type="button" class="deadline-title" data-deadline-detail="${row.index}">${esc(row.package_name||row.plan_name||code)}</button><small>${esc(code)} · ${esc(row.investor_name||'Chưa có chủ đầu tư')}</small></div><time>${esc(row.bid_close_date||'—')}</time><span class="deadline-time ${hours<=24?'urgent':hours<=72?'soon':''}">${remainingTime(row.bid_close_date)}</span></article>`;
  }).join(''):'<p class="empty-inline">Chưa có gói sắp đến hạn trong dữ liệu đã tải. Hãy tra cứu TBMT để cập nhật.</p>';
}
function renderTrackingList() {
  $('trackingList').innerHTML=state.watchlist.length?state.watchlist.map(item=>{
    const inResults=state.rows.find(row=>watchedCode(row)===item.code);
    const url=/^https:\/\/muasamcong\.mpi\.gov\.vn\/web\/guest\/contractor-selection\?/.test(item.url||'')?item.url:'';
    const name=esc(item.name||item.code);
    return `<article class="tracking-item"><div><strong>${name}</strong><small>${esc(item.code)} · ${esc(item.investor||'Chưa có chủ đầu tư')}</small></div><span class="deadline-time">${remainingTime(item.deadline)}</span><div class="tracking-actions">${inResults?`<button class="btn ghost" data-tracking-detail="${inResults.index}">Chi tiết</button>`:''}${url?`<a class="btn ghost" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Mở e-GP ↗</a>`:''}<button class="btn ghost" data-unwatch="${esc(item.code)}">Bỏ theo dõi</button></div></article>`;
  }).join(''):'<p class="empty-inline">Chưa có gói nào được theo dõi. Tới Tra cứu và bấm Theo dõi ở dòng cần lưu.</p>';
}
function renderHistoryList() {
  const list=recentQueries();
  $('historyList').innerHTML=list.length?list.map((item,index)=>`<article class="history-item"><div><strong>${esc(item.keyword||'Tất cả TBMT')}</strong><small>${esc(item.mode)} · ${esc(item.date_from||'')} → ${esc(item.date_to||'')}</small></div><time>${new Date(item.time).toLocaleString('vi-VN')}</time><button class="btn ghost" data-rerun="${index}">Chạy lại</button></article>`).join(''):'<p class="empty-inline">Chưa có truy vấn gần đây trên phiên bản web này.</p>';
}
function renderDownloadLibrary() {
  $('downloadLibrary').innerHTML=state.lotFiles.length?`<h3>File phân lô đã tạo</h3>${state.lotFiles.map(file=>`<a class="library-file" href="${esc(file.url)}" download="${esc(file.name)}"><i data-lucide="download" aria-hidden="true"></i> ${esc(file.name)}</a>`).join('')}`:'<p class="empty-inline">Chưa tạo file phân lô trong phiên làm việc này.</p>';
}
async function refreshApiStatus() {
  try { await api('/api/health');$('apiStatus').textContent='API sẵn sàng';$('apiStatus').classList.add('online'); }
  catch { $('apiStatus').textContent='API mất kết nối';$('apiStatus').classList.remove('online'); }
}
const baseRender=render;
render=function(updateAnalysis=false){baseRender(updateAnalysis);renderUpcoming();if(document.body.dataset.view==='tracking')renderTrackingList();};
const baseRenderRecent=renderRecent;
renderRecent=function(){baseRenderRecent();renderHistoryList();};
const baseRenderLots=renderLotDownloads;
renderLotDownloads=function(){baseRenderLots();renderDownloadLibrary();};

document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.view)));
document.querySelectorAll('[data-go-view]').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.goView)));
document.querySelector('.hero-link').addEventListener('click',event=>{event.preventDefault();showView('search');$('keyword').focus();});
$('collapseSidebar').addEventListener('click',()=>{document.body.classList.toggle('sidebar-collapsed');writeLocal('msc_sidebar',document.body.classList.contains('sidebar-collapsed')?'collapsed':'open');});
$('mobileMenu').addEventListener('click',()=>document.querySelector('.sidebar').classList.toggle('mobile-open'));
$('refreshData').addEventListener('click',()=>{if(state.loading)return;showView('search');if(state.jobId)void startSearch(undefined,true);else void refreshApiStatus();});
$('searchFormFilter').addEventListener('change',()=>{state.pendingFormFilter=$('searchFormFilter').value;state.page=1;applyView();});
$('searchLocationFilter').addEventListener('change',()=>{state.pendingLocationFilter=$('searchLocationFilter').value;state.page=1;applyView();});
$('pageSize').addEventListener('change',()=>{state.page=1;render();});
$('prevPage').addEventListener('click',()=>{state.page--;render();});
$('nextPage').addEventListener('click',()=>{state.page++;render();});
$('resultBody').addEventListener('click',event=>{
  if(event.altKey){const cell=event.target.closest('td');if(cell){const value=cell.innerText.trim();if(value)void copyText(value).then(()=>toast('Đã sao chép ô.'));return;}}
  const watch=event.target.closest('[data-watch]');if(watch){const row=state.rows.find(item=>item.index===Number(watch.dataset.watch));if(row)void toggleWatch(row);return;}
  const copy=event.target.closest('[data-copy-value]');if(copy){void copyText(copy.dataset.copyValue).then(()=>toast(`Đã sao chép ${copy.dataset.copyValue}.`));return;}
  if(event.target.closest('a,button,input,select,label'))return;
  const tr=event.target.closest('tr[data-index]');if(tr)openDetail(Number(tr.dataset.index));
});
$('resultBody').addEventListener('dblclick',event=>{const tr=event.target.closest('tr[data-index]');if(tr&&!event.target.closest('a,button,input'))openDetail(Number(tr.dataset.index));});
$('upcomingDeadlines').addEventListener('click',event=>{const button=event.target.closest('[data-deadline-detail]');if(button)openDetail(Number(button.dataset.deadlineDetail));});
$('trackingList').addEventListener('click',event=>{const detail=event.target.closest('[data-tracking-detail]');if(detail){openDetail(Number(detail.dataset.trackingDetail));return;}const remove=event.target.closest('[data-unwatch]');if(remove){const row=state.rows.find(item=>watchedCode(item)===remove.dataset.unwatch)||{notify_no:remove.dataset.unwatch};void toggleWatch(row);}});
$('historyList').addEventListener('click',event=>{const button=event.target.closest('[data-rerun]');if(button){const entry=recentQueries()[Number(button.dataset.rerun)];if(entry?.mode==='Kho dữ liệu'&&typeof restoreLocalSearch==='function'){restoreLocalSearch(entry);return;}loadRecent(Number(button.dataset.rerun));showView('search');startSearch();}});
$('exportAllWorkspace').addEventListener('click',()=>download('/api/export',false,'Ket_qua.xlsx'));
$('exportSelectedWorkspace').addEventListener('click',()=>download('/api/export',true,'Ket_qua.xlsx'));
$('openLotDownloads').addEventListener('click',()=>{showView('search');$('lotDownloads').scrollIntoView({behavior:'smooth'});});
$('settingsTheme').addEventListener('click',()=>$('themeToggle').click());
$('settingsFolder').addEventListener('click',chooseFolder);
document.querySelectorAll('#results thead th:not(.check-col)').forEach(th=>{
  const grip=document.createElement('span');grip.className='column-grip';grip.title='Kéo để đổi độ rộng cột';th.appendChild(grip);
  grip.addEventListener('click',event=>event.stopPropagation());
  grip.addEventListener('pointerdown',event=>{
    event.preventDefault();event.stopPropagation();grip.setPointerCapture(event.pointerId);
    const startX=event.clientX, startWidth=th.getBoundingClientRect().width;
    const move=event=>{const width=Math.max(90,startWidth+event.clientX-startX);th.style.width=`${width}px`;th.style.minWidth=`${width}px`;};
    const stop=()=>{grip.removeEventListener('pointermove',move);grip.removeEventListener('pointerup',stop);};
    grip.addEventListener('pointermove',move);grip.addEventListener('pointerup',stop);
  });
});
if(readLocal('msc_sidebar','open')==='collapsed')document.body.classList.add('sidebar-collapsed');
showView(window.location.hash.slice(1)||viewForLocation(),false);renderUpcoming();renderHistoryList();renderTrackingList();renderDownloadLibrary();setTimeout(()=>void loadWatchlist(),0);void loadHistory();void refreshApiStatus();setInterval(refreshApiStatus,30000);
window.addEventListener('popstate',()=>showView(viewForLocation(),false));
window.addEventListener('hashchange',()=>showView(window.location.hash.slice(1)));
