const labels={total_users:'Tài khoản',active_users:'Đang hoạt động',searches_today:'Truy vấn hôm nay',saved_searches:'Bộ lọc đã lưu',followed_tenders:'Gói theo dõi',notifications_generated:'Thông báo',downloads:'Lượt xuất file',saved_reports:'Báo cáo đã lưu',report_runs:'Lượt chạy báo cáo',custom_dashboards:'Dashboard riêng',automation_active_rules:'Rule tự động đang bật',automation_runs_today:'Rule chạy hôm nay',automation_matches_today:'Gói khớp rule hôm nay',automation_failures_today:'Lỗi rule hôm nay',automation_average_duration_ms:'Thời gian rule trung bình (ms)'};
const safe=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
async function loadAdmin(){try{
  const response=await fetch('/api/admin/stats');
  if(response.status===401){location.assign('/login');return;}
  if(response.status===403){document.getElementById('adminStatus').textContent='Tài khoản này không có quyền quản trị.';return;}
  const data=await response.json();if(!response.ok)throw new Error(data.error||'Không lấy được dữ liệu.');
  document.getElementById('adminStatus').textContent='Dữ liệu hệ thống hiện tại';
  document.getElementById('adminStats').innerHTML=Object.entries(labels).map(([key,label])=>
    `<article><span>${safe(label)}</span><strong>${Number(data[key]||0).toLocaleString('vi-VN')}</strong></article>`).join('');
  const triggers=data.automation_top_triggers||[];
  document.getElementById('adminAutomation').innerHTML=triggers.length?
    `<section><h2>Trigger automation phổ biến</h2>${triggers.map(item=>
      `<p>${safe(item.trigger)} · ${Number(item.count||0).toLocaleString('vi-VN')} rule</p>`).join('')}</section>`:'';
  document.getElementById('adminJobs').innerHTML=(data.recent_jobs||[]).length?data.recent_jobs.map(job=>
    `<article class="admin-job"><strong>${safe(job.kind)}</strong><span>${safe(job.status)}</span><small>${safe(job.created_at)}</small></article>`).join(''):'<p>Chưa có job nền nào.</p>';
}catch(error){document.getElementById('adminStatus').textContent=error.message;}}
void loadAdmin();
async function loadAdminAi(){try{const response=await fetch('/api/admin/ai-stats');const data=await response.json();if(!response.ok)throw new Error(data.error||'Không lấy được số liệu AI.');const metrics={documents:'Hồ sơ tải lên',source_documents:'Tài liệu nguồn',source_metadata_only:'Chỉ metadata',source_downloaded:'Đã lưu file nguồn',source_failed:'Lỗi file nguồn',document_versions:'Phiên bản',analyses:'Phân tích AI',requests_today:'Lượt AI hôm nay',input_tokens:'Token đầu vào',output_tokens:'Token đầu ra',extraction_failures:'Lỗi trích xuất'};document.getElementById('adminAiStatus').textContent=data.estimated_cost===null?'Chi phí chưa cấu hình đơn giá; token là số đo thực từ provider.':`Chi phí ước tính theo đơn giá cấu hình: ${safe(data.estimated_cost)}`;document.getElementById('adminAiStats').innerHTML=Object.entries(metrics).map(([key,label])=>`<article><span>${safe(label)}</span><strong>${Number(data[key]||0).toLocaleString('vi-VN')}</strong></article>`).join('')+`<article><span>Dung lượng đã lưu</span><strong>${(Number(data.document_storage_bytes||0)/1048576).toFixed(1)} MB</strong></article><article><span>Thời gian trích xuất trung bình</span><strong>${data.average_processing_ms===null?'Chưa có':`${Number(data.average_processing_ms).toLocaleString('vi-VN')} ms`}</strong></article>`;document.getElementById('adminAiModels').innerHTML=(data.by_model||[]).length?`<h3>Theo model</h3>${data.by_model.map(item=>`<p>${safe(item.model)} · ${Number(item.requests).toLocaleString('vi-VN')} lượt · ${Number(item.input_tokens||0).toLocaleString('vi-VN')} token vào · ${Number(item.output_tokens||0).toLocaleString('vi-VN')} token ra</p>`).join('')}`:'<p>Chưa có lượt gọi AI.</p>';document.getElementById('adminAiModels').innerHTML+='<h3>Theo tài khoản</h3>'+((data.by_user||[]).map(item=>`<p>${safe(item.email)} · ${Number(item.requests).toLocaleString('vi-VN')} lượt · ${Number(item.input_tokens||0).toLocaleString('vi-VN')} token vào · ${Number(item.output_tokens||0).toLocaleString('vi-VN')} token ra</p>`).join('')||'<p>Chưa có lượt gọi AI.</p>');}catch(error){document.getElementById('adminAiStatus').textContent=error.message;}}
void loadAdminAi();
async function loadAdminSearchMetrics(){
  if(!document.getElementById('adminSearchStatus'))return;
  try {
    const response=await fetch('/api/intelligence/admin/search-metrics?days=14');
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||'Không lấy được số liệu tìm kiếm.');
    document.getElementById('adminSearchStatus').textContent='Số liệu tổng hợp 14 ngày; không lưu nội dung tìm kiếm của tài khoản.';
    const stats=[['Lượt tìm',data.searches],['Độ trễ trung bình',`${data.average_latency_ms} ms`],
      ['Không có kết quả',`${(data.zero_result_rate*100).toFixed(1)}%`],
      ['Dùng cache',`${(data.cache_hit_rate*100).toFixed(1)}%`]];
    document.getElementById('adminSearchStats').innerHTML=stats.map(([label,value])=>
      `<article><span>${safe(label)}</span><strong>${safe(value)}</strong></article>`).join('');
    const kinds={tender:'TBMT',plan:'KHLCNT',investor:'Chủ đầu tư',procurer:'Bên mời thầu',contractor:'Nhà thầu',all:'Tất cả'};
    const counts={};
    for(const item of data.items||[])counts[item.kind]=(counts[item.kind]||0)+Number(item.searches||0);
    document.getElementById('adminSearchTypes').textContent=Object.entries(counts).map(([kind,count])=>
      `${kinds[kind]||kind}: ${count.toLocaleString('vi-VN')}`).join(' · ')||'Chưa có lượt tìm trong kho.';
  }catch(error){document.getElementById('adminSearchStatus').textContent=error.message;}
}
void loadAdminSearchMetrics();
async function loadAdminSync(){try{
  const [healthResponse,syncResponse]=await Promise.all([
    fetch('/api/intelligence/admin/sync'),fetch('/api/data-sync')]);
  const health=await healthResponse.json(),sync=await syncResponse.json();
  if(!healthResponse.ok)throw new Error(health.error||'Không lấy được chất lượng dữ liệu.');
  if(!syncResponse.ok)throw new Error(sync.error||'Không lấy được trạng thái đồng bộ.');
  const data=health.data||{};
  const healthMetrics=sync.metrics||{};
  const metrics={queue_length:(sync.jobs||[]).filter(item=>['queued','pending','retry','retrying','running'].includes(item.status)).length,
    success_rate:healthMetrics.success_rate??100,average_latency_ms:healthMetrics.average_latency_ms||0,
    cache_hit_rate:healthMetrics.cache_hit_rate||0,failure_count:healthMetrics.failure_count||0};
  const metricLabels={queue_length:'Đang chờ xử lý',success_rate:'Tỷ lệ thành công (%)',average_latency_ms:'Độ trễ trung bình (ms)',cache_hit_rate:'Cache hit (%)',failure_count:'Request lỗi'};
  const source=(sync.sources||[])[0];
  const checkpoint=(sync.checkpoints||[]).find(item=>item.source_id===source?.id);
  const toggle=document.getElementById('adminSyncToggle');
  toggle.dataset.enabled=String(Boolean(source?.is_enabled));
  toggle.textContent=source?.is_enabled?'Tạm dừng nguồn':'Bật nguồn';
  toggle.innerHTML=`<i data-lucide="${source?.is_enabled?'pause':'play'}" aria-hidden="true"></i>${source?.is_enabled?'Tạm dừng nguồn':'Bật nguồn'}`;
  document.getElementById('adminSyncStatus').textContent=source?
    `${source.name} · ${source.is_enabled?'Đang bật':'Tạm dừng'} · Thành công gần nhất: ${checkpoint?.last_success_at?new Date(checkpoint.last_success_at).toLocaleString('vi-VN'):'Chưa có'} · Lần tới: ${source.next_run_at?new Date(source.next_run_at).toLocaleString('vi-VN'):'Chưa đặt lịch'}`:
    'Chưa có nguồn đồng bộ.';
  const badge=document.getElementById('adminSourceBadge'),healthStatus=healthMetrics.status||'Healthy';
  badge.className=`sync-badge ${healthStatus.toLowerCase()}`;badge.innerHTML=Number(healthMetrics.request_count||0)?`<i data-lucide="${healthStatus==='Healthy'?'check-circle':healthStatus==='Degraded'?'alert-triangle':'x-circle'}" aria-hidden="true"></i>${safe(healthStatus)} · Circuit ${safe(healthMetrics.circuit||'CLOSED')}`:'<i data-lucide="activity" aria-hidden="true"></i>Chưa có mẫu nguồn';
  if(Number(healthMetrics.invalid_response_count||0)>=3){badge.className='sync-badge degraded';badge.innerHTML='<i data-lucide="alert-triangle" aria-hidden="true"></i>Cảnh báo định dạng nguồn';badge.title='Nhiều phản hồi nguồn không đúng JSON/định dạng dự kiến. Kiểm tra log và parser.';}
  document.getElementById('adminSyncStats').innerHTML=Object.entries(metrics).map(([key,value])=>
    `<article><span>${safe(metricLabels[key])}</span><strong>${Number(value||0).toLocaleString('vi-VN')}</strong></article>`).join('');
  const jobs=sync.jobs||[];
  document.getElementById('adminSyncJobs').innerHTML=jobs.length?`<table class="sync-table"><thead><tr><th>Job / Entity</th><th>Ưu tiên</th><th>Trạng thái</th><th>Lần thử</th><th>Bắt đầu</th><th>Lỗi gần nhất</th><th>Thao tác</th></tr></thead><tbody>${jobs.map(job=>`<tr><td><strong>${safe(job.job_type)}</strong><br><code>${safe(job.entity_id)}</code></td><td>${safe(job.priority||'normal')}</td><td><span class="job-status ${safe(job.status)}">${safe(job.status)}</span></td><td>${Number(job.attempts||0)}/${Number(job.max_attempts||3)}</td><td>${job.started_at?safe(new Date(job.started_at).toLocaleString('vi-VN')):'—'}</td><td title="${safe(job.last_error||'')}">${safe((job.last_error||'—').slice(0,55))}</td><td><div class="job-actions">${job.status==='failed'?`<button class="sync-button" type="button" data-sync-retry="${job.id}">Thử lại</button>`:''}${['queued','pending','retry','retrying'].includes(job.status)?`<button class="sync-button" type="button" data-sync-cancel="${job.id}">Hủy</button>`:''}</div></td></tr>`).join('')}</tbody></table>`:'<p>Hàng đợi đang trống.</p>';
  document.getElementById('adminSyncRuns').innerHTML=(sync.runs||[]).length?sync.runs.slice(0,12).map(run=>{const total=Number(run.queued_count||0),done=Number(run.processed_count||0),percent=total?Math.round(done*100/total):100;return `<article class="sync-run"><header><strong>${safe(run.mode)} · ${safe(run.status)}</strong><span>${percent}%</span></header><div class="sync-progress" role="progressbar" aria-valuenow="${percent}" aria-valuemin="0" aria-valuemax="100"><span style="width:${percent}%"></span></div><p>${Number(run.success_count||0)} thành công · ${Number(run.failed_count||0)} lỗi / ${total} mục</p><small>${safe(new Date(run.created_at).toLocaleString('vi-VN'))}</small></article>`;}).join(''):'<p>Chưa có lượt đồng bộ.</p>';
  if(window.lucide)window.lucide.createIcons();
}catch(error){document.getElementById('adminSyncStatus').textContent=error.message;}}
async function adminSyncAction(path,body){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw new Error(data.error||'Không chạy được đồng bộ.');await loadAdminSync();}
document.getElementById('adminSyncStart').addEventListener('click',event=>{event.currentTarget.disabled=true;adminSyncAction('/api/data-sync/runs',{mode:'stale',limit:100}).catch(error=>{document.getElementById('adminSyncStatus').textContent=error.message;}).finally(()=>{event.currentTarget.disabled=false;});});
document.getElementById('adminSyncProcess').addEventListener('click',event=>{event.currentTarget.disabled=true;adminSyncAction('/api/data-sync/process',{limit:5}).catch(error=>{document.getElementById('adminSyncStatus').textContent=error.message;}).finally(()=>{event.currentTarget.disabled=false;});});
document.getElementById('adminSyncToggle').addEventListener('click',event=>{const enabled=event.currentTarget.dataset.enabled==='true';event.currentTarget.disabled=true;adminSyncAction(`/api/data-sync/sources/egp-public/${enabled?'pause':'enable'}`,{}).catch(error=>{document.getElementById('adminSyncStatus').textContent=error.message;}).finally(()=>{event.currentTarget.disabled=false;});});
document.getElementById('adminSyncCleanup').addEventListener('click',event=>{event.currentTarget.disabled=true;adminSyncAction('/api/data-sync/cleanup',{}).catch(error=>{document.getElementById('adminSyncStatus').textContent=error.message;}).finally(()=>{event.currentTarget.disabled=false;});});
document.getElementById('adminForceSync').addEventListener('submit',event=>{event.preventDefault();const button=event.currentTarget.querySelector('button'),input=document.getElementById('adminForceCode');button.disabled=true;adminSyncAction('/api/data-sync/force',{entity_id:input.value.trim()}).then(()=>{input.value='';}).catch(error=>{document.getElementById('adminSyncStatus').textContent=error.message;}).finally(()=>{button.disabled=false;});});
document.getElementById('adminSyncJobs').addEventListener('click',event=>{const retry=event.target.closest('[data-sync-retry]'),cancel=event.target.closest('[data-sync-cancel]'),button=retry||cancel;if(!button)return;button.disabled=true;adminSyncAction(`/api/data-sync/jobs/${retry?retry.dataset.syncRetry:cancel.dataset.syncCancel}/${retry?'retry':'cancel'}`,{}).catch(error=>{document.getElementById('adminSyncStatus').textContent=error.message;}).finally(()=>{button.disabled=false;});});
if(window.lucide)window.lucide.createIcons();
void loadAdminSync();
