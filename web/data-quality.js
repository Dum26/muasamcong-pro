(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g,
    char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const date = value => value ? new Date(value).toLocaleString('vi-VN') : '—';
  let page = 1, currentIssues = [];
  async function request(path, body) {
    const response = await fetch(path, body === undefined ? {} : {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Không lấy được dữ liệu.');
    return data;
  }
  function issueRow(item) {
    const actions = ['open','reviewing'].includes(item.status) ?
      `${item.rule_code === 'TENDER_EXTRA_WHITESPACE' ? `<button class="sync-button" data-dq-fix="${item.id}">Chuẩn hóa</button>` : ''}
       ${item.status === 'open' ? `<button class="sync-button quiet" data-dq-action="review" data-id="${item.id}">Đang xem</button>` : ''}
       <button class="sync-button quiet" data-dq-action="resolve" data-id="${item.id}">Đã xử lý</button>
       <button class="sync-button quiet" data-dq-action="ignore" data-id="${item.id}">Bỏ qua</button>` : esc(item.status);
    return `<tr><td><span class="dq-severity ${esc(item.severity)}">${esc(item.severity)}</span></td>
      <td><code>${esc(item.entity_type)} · ${esc(item.entity_id)}</code></td>
      <td>${esc(item.field_name || '—')}</td><td>${esc(item.rule_code)}</td>
      <td><button type="button" class="dq-detail-button" data-dq-detail="${item.id}">${esc(item.message)}</button></td>
      <td>${esc(date(item.detected_at))}</td><td><div class="dq-actions">${actions}</div></td></tr>`;
  }
  function duplicateCard(item) {
    const side = entity => `<div><strong>${esc(entity?.name || 'Không còn bản ghi')}</strong>
      <small>${esc(entity?.tax_code || entity?.identifier || 'Chưa có mã định danh')}</small>
      <small>${esc(entity?.address || 'Chưa có địa chỉ')}</small></div>`;
    return `<article class="dq-candidate"><div class="dq-pair">${side(item.entity_a)}${side(item.entity_b)}</div>
      <p>${esc(item.entity_type)} · ${(Number(item.confidence)*100).toFixed(0)}% · Trùng ${esc(item.reason_json?.matching_field || 'định danh')}</p>
      <div class="dq-actions"><button class="sync-button" data-dq-merge="${esc(item.entity_id_a)}" data-id="${item.id}">Giữ bản ghi bên trái</button>
      <button class="sync-button" data-dq-merge="${esc(item.entity_id_b)}" data-id="${item.id}">Giữ bản ghi bên phải</button>
      <button class="sync-button" data-dq-duplicate="not_duplicate" data-id="${item.id}">Không trùng</button>
      <button class="sync-button quiet" data-dq-duplicate="ignore" data-id="${item.id}">Bỏ qua</button></div></article>`;
  }
  async function load() {
    try {
      const params = new URLSearchParams({page:String(page),status:$('dqFilterStatus').value,
        severity:$('dqFilterSeverity').value,entity_type:$('dqFilterEntity').value});
      const [summary,issues,duplicates,runs] = await Promise.all([
        request('/api/admin/data-quality/summary'),
        request('/api/admin/data-quality/issues?'+params),
        request('/api/admin/data-quality/duplicates'),
        request('/api/admin/data-quality/runs')]);
      currentIssues = issues.items;
      $('dqStats').innerHTML = [['Bản ghi chưa có vấn đề',summary.records_without_open_issues_pct===null?'Chưa quét đủ':`${summary.records_without_open_issues_pct}%`],
        ['Gói có giá hợp lệ',`${summary.tenders_with_valid_price}/${summary.tender_count}`],
        ['Đang mở',summary.open],['Mới trong 24 giờ',summary.new_24h],
        ['Nghiêm trọng',summary.critical],['Cảnh báo',summary.warnings],
        ['Dữ liệu cũ',summary.stale],['Liên kết lỗi',summary.broken_relations],
        ['Cảnh báo nguồn',summary.source_alerts],
        ['Đã xử lý',summary.resolved],['Nghi trùng',summary.duplicates_pending]]
        .map(([label,value]) => `<article><span>${esc(label)}</span><strong>${typeof value==='number'?value.toLocaleString('vi-VN'):esc(value)}</strong></article>`).join('');
      const run = summary.latest_run;
      $('dqStatus').textContent = run ? `Lượt quét ${run.run_type} · ${run.status} · ${run.entities_scanned} đối tượng đã kiểm tra` : 'Chưa chạy lượt kiểm tra nào.';
      $('dqIssues').innerHTML = issues.items.length ?
        `<table class="dq-issues"><thead><tr><th>Mức độ</th><th>Đối tượng</th><th>Trường</th><th>Quy tắc</th><th>Nguyên nhân</th><th>Phát hiện</th><th>Thao tác</th></tr></thead><tbody>${issues.items.map(issueRow).join('')}</tbody></table>` :
        '<div class="dq-empty">Không phát hiện vấn đề dữ liệu trong bộ lọc này.</div>';
      $('dqPage').textContent = `Trang ${page} · ${issues.total} vấn đề`;
      $('dqPrev').disabled = page <= 1; $('dqNext').disabled = !issues.has_more;
      $('dqDuplicates').innerHTML = duplicates.items.length ? duplicates.items.map(duplicateCard).join('') : '<p>Chưa có cặp nghi trùng.</p>';
      $('dqRuns').innerHTML = runs.items.length ? `<div class="sync-table-wrap"><table class="dq-issues"><thead><tr><th>Bắt đầu</th><th>Loại</th><th>Trạng thái</th><th>Đã kiểm tra</th><th>Phát hiện</th><th>Tự hết lỗi</th></tr></thead><tbody>${runs.items.map(item=>`<tr><td>${esc(date(item.created_at))}</td><td>${esc(item.run_type)}</td><td>${esc(item.status)}</td><td>${esc(item.entities_scanned)}</td><td>${esc(item.issues_found)}</td><td>${esc(item.issues_resolved)}</td></tr>`).join('')}</tbody></table></div>` : 'Chưa có lượt quét.';
    } catch (error) { $('dqStatus').textContent = error.message; }
  }
  async function action(button,path,body) {
    button.disabled = true;
    try { await request(path,body); await load(); }
    catch (error) { $('dqStatus').textContent = error.message; }
    finally { button.disabled = false; }
  }
  $('dqIncremental').addEventListener('click',event => void action(event.currentTarget,'/api/admin/data-quality/scan',{run_type:'incremental'}));
  $('dqFull').addEventListener('click',event => { if (confirm('Quét toàn bộ dữ liệu hiện có? Lượt quét được chia thành nhiều lô.')) void action(event.currentTarget,'/api/admin/data-quality/scan',{run_type:'full'}); });
  $('dqProcess').addEventListener('click',event => void action(event.currentTarget,'/api/admin/data-quality/scan/process',{}));
  $('dqRefresh').addEventListener('click',() => void load());
  for (const id of ['dqFilterStatus','dqFilterSeverity','dqFilterEntity']) $(id).addEventListener('change',() => { page=1; void load(); });
  $('dqPrev').addEventListener('click',() => { if(page>1){page--;void load();} });
  $('dqNext').addEventListener('click',() => {page++;void load();});
  $('dqIssues').addEventListener('click',event => {
    const fix=event.target.closest('[data-dq-fix]');
    if(fix){fix.disabled=true;void request(`/api/admin/data-quality/issues/${fix.dataset.dqFix}/fix`,{}).then(async result=>{
      await load();const status=$('dqStatus');status.textContent=`Đã chuẩn hóa tên gói. Mã hoàn tác: ${result.fix_id}.`;
      const revert=document.createElement('button');revert.type='button';revert.className='sync-button quiet';
      revert.dataset.dqRevert=result.fix_id;revert.textContent='Hoàn tác';status.append(' ',revert);
    }).catch(error=>{$('dqStatus').textContent=error.message;fix.disabled=false;});return;}
    const detail=event.target.closest('[data-dq-detail]');
    if(detail){void request(`/api/admin/data-quality/issues/${detail.dataset.dqDetail}`).then(data=>{
      const item=data.issue,panel=$('dqDetail');panel.hidden=false;
      panel.innerHTML=`<h3>${esc(item.rule_code)}</h3><p>${esc(data.rule_description)}</p>
        <dl><dt>Đối tượng</dt><dd>${esc(item.entity_type)} · ${esc(item.entity_id)}</dd>
        <dt>Giá trị hiện tại</dt><dd>${esc(data.current_value??'Chưa có')}</dd>
        <dt>Lý do</dt><dd>${esc(item.message)}</dd><dt>Bằng chứng</dt>
        <dd><pre>${esc(JSON.stringify(item.details_json||{},null,2))}</pre></dd></dl>
        ${/^https:\/\/muasamcong\.mpi\.gov\.vn\//.test(data.source_url||'')?`<a href="${esc(data.source_url)}" target="_blank" rel="noopener noreferrer">Mở nguồn ↗</a>`:''}
        <p>${(data.snapshots||[]).length?`Snapshot gần đây: ${data.snapshots.map(row=>`v${row.version} (${esc(date(row.created_at))})`).join(' · ')}`:'Chưa có snapshot cho đối tượng này.'}</p>`;
      panel.scrollIntoView({block:'nearest',behavior:'smooth'});
    }).catch(error=>{$('dqStatus').textContent=error.message;});return;}
    const button=event.target.closest('[data-dq-action]');
    if(button)void action(button,`/api/admin/data-quality/issues/${button.dataset.id}/${button.dataset.dqAction}`,{});
  });
  $('dqStatus').addEventListener('click',event=>{const button=event.target.closest('[data-dq-revert]');
    if(button)void action(button,`/api/admin/data-quality/fixes/${button.dataset.dqRevert}/revert`,{});});
  $('dqDuplicates').addEventListener('click',event=>{
    const merge=event.target.closest('[data-dq-merge]');
    if(merge){
      if(confirm('Gộp hai pháp nhân có cùng định danh? Các liên kết sẽ chuyển sang bản ghi được giữ và lịch sử được lưu.'))
        void action(merge,`/api/admin/data-quality/duplicates/${merge.dataset.id}/merge`,{target_id:merge.dataset.dqMerge});
      return;
    }
    const button=event.target.closest('[data-dq-duplicate]');
    if(button)void action(button,`/api/admin/data-quality/duplicates/${button.dataset.id}/${button.dataset.dqDuplicate}`,{});
  });
  void load();
})();
