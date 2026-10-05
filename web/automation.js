/* MuaSamCong Pro automation workspace. All decisions and actions run on server. */
const autoState={schema:null,rules:[],view:'list',editing:null,detail:null,detailTab:'overview',
  runs:[],request:0,preview:null,analytics:null};
const autoEl=id=>document.getElementById(id);
const autoLabels={title:'Tên gói',tender_code:'Mã TBMT',khlcnt_code:'Mã KHLCNT',
  investor_name:'Chủ đầu tư',procuring_entity_name:'Bên mời thầu',winning_contractor:'Nhà thầu',
  location:'Địa điểm',package_price:'Giá gói',winning_price:'Giá trúng',status:'Trạng thái',
  selection_method:'Hình thức LCNT',contract_type:'Loại hợp đồng',publish_date:'Ngày đăng',
  bid_closing_date:'Hạn đóng thầu',result_date:'Ngày KQLCNT',is_followed:'Đang theo dõi',
  tag:'Tag',changed_field:'Trường thay đổi',saved_search:'Bộ lọc đã lưu'};
const autoActionLabels={FOLLOW_TENDER:'Theo dõi gói',UNFOLLOW_TENDER:'Bỏ theo dõi',
  ADD_TAG:'Thêm tag',REMOVE_TAG:'Xóa tag',SET_PRIORITY:'Đặt ưu tiên',
  SET_INTERNAL_STATUS:'Đặt trạng thái nội bộ',CREATE_NOTIFICATION:'Tạo thông báo',
  ADD_NOTE_TEMPLATE:'Thêm ghi chú',QUEUE_DOCUMENT_CHECK:'Kiểm tra tài liệu mới'};
const autoFieldOps={text:[['equals','Bằng'],['not_equals','Khác'],['contains','Chứa'],
  ['not_contains','Không chứa'],['starts_with','Bắt đầu bằng'],['ends_with','Kết thúc bằng']],
  number:[['equal','Bằng'],['not_equals','Khác'],['greater_than','Lớn hơn'],
  ['greater_or_equal','Từ'],['less_than','Nhỏ hơn'],['less_or_equal','Đến'],['between','Trong khoảng']],
  date:[['equals','Đúng ngày'],['before','Trước'],['after','Sau'],
  ['between','Trong khoảng'],['within_days','Trong N ngày tới']],
  boolean:[['is','Là'],['is_not','Không là']]};
const autoTemplates={
  new:{name:'Gói mới theo từ khóa',trigger_type:'NEW_TENDER',conditions:{logic:'AND',items:[
    {field:'title',operator:'contains',value:'thiết bị'}]},actions:[{type:'FOLLOW_TENDER',value:''},
    {type:'CREATE_NOTIFICATION',value:''}]},
  deadline:{name:'Gói sắp đóng trong 3 ngày',trigger_type:'DEADLINE_APPROACHING',
    conditions:{logic:'AND',items:[{field:'bid_closing_date',operator:'within_days',value:3},
      {field:'is_followed',operator:'is',value:true}]},actions:[{type:'CREATE_NOTIFICATION',value:''}]},
  result:{name:'Gói theo dõi có KQLCNT',trigger_type:'KQLCNT_AVAILABLE',
    conditions:{logic:'AND',items:[{field:'is_followed',operator:'is',value:true}]},
    actions:[{type:'CREATE_NOTIFICATION',value:''}]},
  price:{name:'Gói có giá thay đổi',trigger_type:'PRICE_CHANGED',
    conditions:{logic:'AND',items:[]},actions:[{type:'CREATE_NOTIFICATION',value:''}]},
  document:{name:'Gói theo dõi có tài liệu mới',trigger_type:'NEW_DOCUMENT',
    conditions:{logic:'AND',items:[{field:'is_followed',operator:'is',value:true}]},
    actions:[{type:'QUEUE_DOCUMENT_CHECK',value:''},{type:'CREATE_NOTIFICATION',value:''}]},
  saved:{name:'Bộ lọc đã lưu có kết quả',trigger_type:'SAVED_SEARCH_MATCH',
    conditions:{logic:'AND',items:[{field:'saved_search',operator:'equals',value:''}]},
    actions:[{type:'FOLLOW_TENDER',value:''},{type:'CREATE_NOTIFICATION',value:''}]}
};

async function autoJson(path,options){return (await api(path,options)).json();}
function autoStatus(message,error=false){autoEl('automationStatus').textContent=message;
  autoEl('automationStatus').classList.toggle('data-error',error);}
function autoTime(value){if(!value)return 'Chưa chạy';const date=new Date(value);
  return Number.isNaN(date.getTime())?esc(value):date.toLocaleString('vi-VN');}
function autoEmpty(message){return `<div class="automation-empty">${esc(message)}</div>`;}
function autoFieldType(field){const fields=autoState.schema?.fields||{};
  return Object.keys(fields).find(type=>fields[type].includes(field))||'text';}
function autoOptions(entries,current){return entries.map(([value,label])=>
  `<option value="${esc(value)}" ${value===current?'selected':''}>${esc(label)}</option>`).join('');}
function autoSummary(){const active=autoState.rules.filter(row=>row.is_enabled).length,
  paused=autoState.rules.length-active;
  autoEl('automationSummary').innerHTML=[['Đang chạy',active],['Tạm dừng',paused],
    ['Lượt chạy gần đây',autoState.summary?.recent_runs||0],
    ['Lượt có lỗi',autoState.summary?.failures||0]].map(([label,value])=>
      `<article class="automation-stat"><span>${esc(label)}</span><strong>${value}</strong></article>`).join('');}
function autoRenderAnalytics(){const target=autoEl('automationAnalytics'),data=autoState.analytics;
  if(!target||!data){if(target)target.innerHTML='';return;}
  const trend=data.trend||[],actions=data.actions||[],max=Math.max(1,...trend.map(item=>Number(item.runs)||0));
  target.innerHTML=`<section><div><h3>Hoạt động ${Number(data.days)||14} ngày</h3>
    <p class="automation-helper">Lượt chạy, gói khớp và lỗi của riêng tài khoản này.</p></div>
    <div class="automation-trend" role="img" aria-label="Biểu đồ lượt chạy automation theo ngày">${trend.length?trend.map(item=>
      `<div class="automation-trend-day" title="${esc(item.day)}: ${Number(item.runs)} lượt, ${Number(item.matches)} gói khớp">
        <span style="height:${Math.max(8,Math.round(Number(item.runs)*100/max))}%"></span><small>${esc(String(item.day).slice(5))}</small></div>`).join(''):
      '<p class="automation-helper">Chưa có lượt chạy.</p>'}</div></section>
    <section><h3>Hành động đã thực hiện</h3><div class="automation-action-stats">${actions.length?actions.map(item=>
      `<span class="automation-badge">${esc(autoActionLabels[item.action]||item.action)} · ${Number(item.count)}</span>`).join(''):
      '<p class="automation-helper">Chưa có hành động thành công.</p>'}</div></section>`;}
function autoRuleText(rule){const items=rule.conditions_json?.items||[];
  const count=items.reduce((sum,item)=>sum+('items' in item?item.items.length:1),0);
  return `${count} điều kiện · ${rule.actions_json?.map(item=>autoActionLabels[item.type]||item.type).join(' → ')||'Chưa có hành động'}`;}
function autoRuleStatus(rule){
  if(rule.last_run_error)return ['Lỗi gần nhất','error'];
  if(!rule.last_run_at)return ['Chưa chạy',''];
  return [rule.is_enabled?'Đang chạy':'Tạm dừng',rule.is_enabled?'active':''];
}
function autoRenderList(){autoState.view='list';autoState.editing=null;
  autoEl('automationContent').innerHTML=autoState.rules.length?
    `<div class="automation-list">${autoState.rules.map(rule=>{const status=autoRuleStatus(rule);return `<article class="automation-card">
      <div><div class="automation-card-head"><h3>${esc(rule.name)}</h3>
        <span class="automation-badge ${status[1]}">${status[0]}</span>
        <span class="automation-badge">${esc(autoState.schema.triggers[rule.trigger_type]||rule.trigger_type)}</span></div>
        <p>${esc(autoRuleText(rule))}</p><small>Lần chạy cuối: ${autoTime(rule.last_run_at)} ·
        Lần tới: ${rule.next_run_at?autoTime(rule.next_run_at):'Thủ công'}</small></div>
      <div class="automation-card-actions"><button type="button" class="btn ghost" data-auto-open="${rule.id}">Chi tiết</button>
        <button type="button" class="btn ghost" data-auto-edit="${rule.id}">Sửa</button>
        <button type="button" class="btn ghost" data-auto-test="${rule.id}">Test</button>
        <button type="button" class="btn ghost" data-auto-run="${rule.id}">Chạy ngay</button>
        <button type="button" class="btn ghost" data-auto-toggle="${rule.id}">${rule.is_enabled?'Tạm dừng':'Bật'}</button></div>
      </article>`}).join('')}</div>`:
    autoEmpty('Chưa có rule trong bộ lọc này. Bấm “Tạo automation” để bắt đầu.');
  autoSummary();}
function autoConditionMarkup(item={field:'title',operator:'contains',value:''}){
  const field=item.field||'title',kind=autoFieldType(field),operators=autoFieldOps[kind]||autoFieldOps.text;
  const value=Array.isArray(item.value)?item.value.join(' → '):item.value??'';
  const control=kind==='boolean'?`<select data-auto-value>${autoOptions([['true','Có'],['false','Không']],String(value))}</select>`:
    `<input data-auto-value value="${esc(value)}" ${kind==='number'?'inputmode="decimal"':''}
      placeholder="${kind==='date'?'YYYY-MM-DD hoặc số ngày':kind==='number'?'Ví dụ: 500000000':'Nhập giá trị'}">`;
  return `<div class="automation-condition" data-auto-condition><label>Trường<select data-auto-field>
    ${autoOptions(Object.keys(autoLabels).map(key=>[key,autoLabels[key]]),field)}</select></label>
    <label>So sánh<select data-auto-operator>${autoOptions(operators,item.operator)}</select></label>
    <label>Giá trị${control}</label><button type="button" class="btn ghost" data-auto-remove-condition aria-label="Xóa điều kiện">Xóa</button></div>`;}
function autoGroupMarkup(group={logic:'AND',items:[]}){
  return `<div class="automation-group" data-auto-group><div class="automation-group-head">
    <label>Trong nhóm này<select data-auto-group-logic>${autoOptions([['AND','Tất cả điều kiện (AND)'],
      ['OR','Một trong các điều kiện (OR)']],group.logic)}</select></label>
    <button type="button" class="btn ghost" data-auto-remove-group>Xóa nhóm</button></div>
    <div data-auto-condition-list>${group.items.map(autoConditionMarkup).join('')}</div>
    <button type="button" class="btn ghost" data-auto-add-condition>+ Điều kiện</button></div>`;}
function autoActionMarkup(item={type:'FOLLOW_TENDER',value:''}){
  let value='';
  if(item.type==='SET_PRIORITY')value=`<select data-auto-action-value>${autoOptions([
    ['Thấp','Thấp'],['Trung bình','Trung bình'],['Cao','Cao'],['Khẩn cấp','Khẩn cấp']],
    item.value||'Cao')}</select>`;
  else if(item.type==='SET_INTERNAL_STATUS')value=`<select data-auto-action-value>${autoOptions([
    ['Mới','Mới'],['Đang xem','Đang xem'],['Quan tâm','Quan tâm'],['Đang xử lý','Đang xử lý'],
    ['Hoàn tất','Hoàn tất'],['Bỏ qua','Bỏ qua']],item.value||'Quan tâm')}</select>`;
  else if(['ADD_TAG','REMOVE_TAG','ADD_NOTE_TEMPLATE'].includes(item.type))value=
    `<input data-auto-action-value value="${esc(item.value||'')}" placeholder="${item.type==='ADD_NOTE_TEMPLATE'?'Có thể dùng {rule_name}, {tender_code}':'Tên tag'}">`;
  return `<div class="automation-action" data-auto-action><label>Hành động<select data-auto-action-type>
    ${autoOptions(Object.entries(autoActionLabels),item.type)}</select></label>
    <label>Thiết lập${value||'<span class="automation-helper">Không cần giá trị</span>'}</label>
    <div class="automation-row-actions"><button type="button" class="btn ghost" data-auto-move="up" title="Lên">↑</button>
    <button type="button" class="btn ghost" data-auto-move="down" title="Xuống">↓</button>
    <button type="button" class="btn ghost" data-auto-remove-action>Xóa</button></div></div>`;}
function autoReadDraft(){const root=autoEl('automationContent');
  const groups=[...root.querySelectorAll('[data-auto-group]')].map(group=>({
    logic:group.querySelector('[data-auto-group-logic]').value,
    items:[...group.querySelectorAll('[data-auto-condition]')].map(row=>{
      const field=row.querySelector('[data-auto-field]').value,
        operator=row.querySelector('[data-auto-operator]').value,
        text=row.querySelector('[data-auto-value]').value.trim();
      return {field,operator,value:operator==='between'?text.split(/\s*→\s*|\s*,\s*/).slice(0,2):
        autoFieldType(field)==='boolean'?text==='true':text};})}));
  const actions=[...root.querySelectorAll('[data-auto-action]')].map(row=>({
    type:row.querySelector('[data-auto-action-type]').value,
    value:row.querySelector('[data-auto-action-value]')?.value.trim()||''}));
  return {name:autoEl('autoName').value.trim(),description:autoEl('autoDescription').value.trim(),
    trigger_type:autoEl('autoTrigger').value,run_frequency:autoEl('autoFrequency').value,
    priority:autoEl('autoPriority').value,is_enabled:autoEl('autoEnabled').checked,
    conditions:{logic:groups.length===1?groups[0].logic:autoEl('autoRootLogic').value,
      items:groups.length===1?groups[0].items:groups},actions};}
function autoRenderBuilder(draft,ruleId=''){
  autoState.view='builder';autoState.editing=ruleId;
  const groups=(draft.conditions?.items||[]).some(item=>'items' in item)?draft.conditions.items:
    [{logic:draft.conditions?.logic||'AND',items:draft.conditions?.items||[]}];
  autoEl('automationContent').innerHTML=`<div class="automation-builder">
    <div class="automation-detail-head"><div><h3>${ruleId?'Sửa automation':'Tạo automation'}</h3>
    <p class="automation-helper">Test trước khi lưu để xem gói khớp; Test không chạy hành động.</p></div>
    <button type="button" class="btn ghost" data-auto-back>Quay lại</button></div>
    <div class="automation-builder-grid"><label>Mẫu nhanh<select id="autoTemplate">
      ${autoOptions([['','Tự tạo'],['new','Gói mới theo từ khóa'],['deadline','Deadline 3 ngày'],
        ['result','Có KQLCNT'],['document','Có tài liệu mới'],['saved','Bộ lọc có kết quả'],
        ['price','Giá thay đổi']],'')}</select></label>
      <label>Tên rule<input id="autoName" maxlength="120" value="${esc(draft.name||'')}" required></label>
      <label>Ưu tiên xử lý<select id="autoPriority">${autoOptions([
        ['low','Thấp'],['normal','Bình thường'],['high','Cao']],draft.priority||'normal')}</select></label></div>
    <label>Mô tả<input id="autoDescription" maxlength="1000" value="${esc(draft.description||'')}"></label>
    <section><h3><span>WHEN</span> Khi nào?</h3><div class="automation-builder-grid">
      <label>Trigger<select id="autoTrigger">${autoOptions(Object.entries(autoState.schema.triggers),draft.trigger_type||'NEW_TENDER')}</select></label>
      <label>Tần suất<select id="autoFrequency">${autoOptions([
        ['manual','Chỉ chạy thủ công'],['hourly','Mỗi giờ'],['3h','Mỗi 3 giờ'],
        ['6h','Mỗi 6 giờ'],['daily','Hàng ngày']],draft.run_frequency||'manual')}</select></label>
      <label><span>Trạng thái</span><span><input id="autoEnabled" type="checkbox" ${draft.is_enabled?'checked':''}> Bật sau khi lưu</span></label></div></section>
    <section><h3><span>IF</span> Nếu thỏa điều kiện</h3>
      <label>Kết hợp nhóm<select id="autoRootLogic">${autoOptions([['AND','Tất cả nhóm (AND)'],
        ['OR','Một trong các nhóm (OR)']],draft.conditions?.logic||'AND')}</select></label>
      <div id="autoGroups" class="automation-groups">${groups.map(autoGroupMarkup).join('')}</div>
      <button type="button" class="btn ghost" data-auto-add-group>+ Thêm nhóm</button>
      <p class="automation-helper">Giá nhập dạng số, ví dụ 500000000. “Trong khoảng” nhập hai giá trị cách nhau bằng dấu phẩy.</p></section>
    <section><h3><span>THEN</span> Thực hiện theo thứ tự</h3>
      <div id="autoActions" class="automation-actions">${(draft.actions||[]).map(autoActionMarkup).join('')}</div>
      <button type="button" class="btn ghost" data-auto-add-action>+ Thêm hành động</button>
      <p class="automation-helper">Các hành động được xử lý theo thứ tự; thông báo chỉ tạo một lần cho mỗi gói/sự kiện.</p></section>
    <div class="automation-builder-actions"><button type="button" class="btn ghost" data-auto-preview>Test rule</button>
      <button type="button" class="btn" data-auto-save>Lưu rule</button>
      <button type="button" class="btn ghost" data-auto-back>Hủy</button></div>
    <div id="autoPreview" aria-live="polite"></div></div>`;
}
function autoDraftNew(){return {name:'',description:'',trigger_type:'NEW_TENDER',
  run_frequency:'manual',priority:'normal',is_enabled:false,
  conditions:{logic:'AND',items:[{field:'title',operator:'contains',value:''}]},
  actions:[{type:'FOLLOW_TENDER',value:''}]};}
function autoFind(id){return autoState.rules.find(item=>item.id===id);}
function autoRenderPreview(result){autoEl('autoPreview').innerHTML=`<div class="automation-preview">
  <strong>${result.matched_count}${result.truncated?'+':''} / ${result.scanned_count} gói phù hợp</strong>
  ${result.truncated?'<p>Chỉ quét 1.000 ứng viên đầu. Hãy thêm điều kiện để xem đủ.</p>':''}
  <p>Đây là bản xem trước; chưa theo dõi, gắn tag hoặc tạo thông báo.</p>
  <ul>${result.items.map(item=>`<li><a href="/app/tenders/${encodeURIComponent(item.tender_code)}">
    ${esc(item.tender_code)}</a> · ${esc(item.title||'Chưa có tên')}</li>`).join('')}</ul></div>`;}
async function autoShowDetail(id,tab='overview'){
  const rule=autoFind(id)||await autoJson('/api/automations/'+id);
  autoState.detail=rule;autoState.view='detail';autoState.detailTab=tab;
  const tabs=[['overview','Tổng quan'],['conditions','Điều kiện'],['actions','Hành động'],
    ['runs','Lượt chạy'],['errors','Lỗi']];
  autoEl('automationContent').innerHTML=`<div class="automation-detail"><div class="automation-detail-head">
    <div><h3>${esc(rule.name)}</h3><p class="automation-helper">${esc(rule.description||autoRuleText(rule))}</p>
      <span class="automation-badge ${rule.is_enabled?'active':''}">${rule.is_enabled?'Đang chạy':'Tạm dừng'}</span></div>
    <button type="button" class="btn ghost" data-auto-back>Danh sách</button></div>
    <div class="automation-card-actions"><button type="button" class="btn ghost" data-auto-edit="${id}">Sửa</button>
      <button type="button" class="btn ghost" data-auto-test="${id}">Test</button>
      <button type="button" class="btn" data-auto-run="${id}">Chạy ngay</button>
      <button type="button" class="btn ghost" data-auto-toggle="${id}">${rule.is_enabled?'Tạm dừng':'Bật'}</button>
      <button type="button" class="btn ghost" data-auto-duplicate="${id}">Nhân bản</button>
      <button type="button" class="btn ghost" data-auto-export="${id}">Xuất JSON</button>
      <button type="button" class="btn ghost" data-auto-delete="${id}">Xóa</button></div>
    <nav class="automation-tabs" aria-label="Chi tiết rule">${tabs.map(([key,label])=>
      `<button type="button" data-auto-tab="${key}" class="${key===tab?'active':''}">${label}</button>`).join('')}</nav>
    <div id="autoDetailBody"></div></div>`;
  await autoRenderDetailTab(tab);
}
async function autoRenderDetailTab(tab){const rule=autoState.detail,target=autoEl('autoDetailBody');
  if(!target)return;
  if(tab==='overview')target.innerHTML=`<p>Khi <strong>${esc(autoState.schema.triggers[rule.trigger_type])}</strong>
    → ${esc(autoRuleText(rule))}</p><p>Ưu tiên: ${esc(rule.priority)} · Tần suất: ${esc(rule.run_frequency)}</p>
    <p>Lần cuối: ${autoTime(rule.last_run_at)} · Lần tới: ${rule.next_run_at?autoTime(rule.next_run_at):'Thủ công'}</p>`;
  else if(tab==='conditions')target.innerHTML=`<pre>${esc(JSON.stringify(rule.conditions_json,null,2))}</pre>`;
  else if(tab==='actions')target.innerHTML=`<ol>${rule.actions_json.map(item=>
    `<li>${esc(autoActionLabels[item.type]||item.type)} ${esc(item.value||'')}</li>`).join('')}</ol>`;
  else {
    const runs=(await autoJson('/api/automations/'+rule.id+'/runs')).items||[];
    const shown=tab==='errors'?runs.filter(item=>item.status==='failed'||item.status==='partial'):runs;
    target.innerHTML=shown.length?`<ul class="automation-run-list">${shown.map(run=>
      `<li class="automation-run"><div><strong>${esc(run.status)}</strong>
      <small> ${autoTime(run.started_at)} · ${run.matched_count} khớp · ${run.action_count} hành động · ${run.duration_ms??0} ms</small>
      ${run.error_message?`<p class="data-error">${esc(run.error_message)}</p>`:''}</div>
      <button type="button" class="btn ghost" data-auto-events="${run.id}">Sự kiện</button></li>`).join('')}</ul>`:
      autoEmpty(tab==='errors'?'Chưa có lượt chạy lỗi.':'Chưa có lượt chạy.');
  }}
async function loadAutomationWorkspace(){const request=++autoState.request;
  autoStatus('Đang tải automation…');
  try{
    const query=new URLSearchParams();
    if(autoEl('automationSearch').value.trim())query.set('q',autoEl('automationSearch').value.trim());
    if(autoEl('automationState').value)query.set('status',autoEl('automationState').value);
    if(autoEl('automationTriggerFilter').value)query.set('trigger',autoEl('automationTriggerFilter').value);
    if(autoEl('automationLastRun').value)query.set('last_run',autoEl('automationLastRun').value);
    const [schema,data,analytics]=await Promise.all([autoState.schema||autoJson('/api/automations/schema'),
      autoJson('/api/automations?'+query),autoJson('/api/automations/analytics?days=14')]);
    if(request!==autoState.request)return;
    autoState.schema=schema;autoState.rules=data.items||[];autoState.summary=data.summary;
    autoState.analytics=analytics;
    if(autoEl('automationTriggerFilter').options.length===1)
      autoEl('automationTriggerFilter').insertAdjacentHTML('beforeend',
        Object.entries(schema.triggers).map(([key,label])=>
          `<option value="${esc(key)}">${esc(label)}</option>`).join(''));
    autoRenderList();autoRenderAnalytics();autoStatus(`${autoState.rules.length} rule trong bộ lọc · Dữ liệu theo tài khoản của bạn.`);
  }catch(error){autoStatus('Không lấy được automation: '+error.message,true);
    autoEl('automationContent').innerHTML=autoEmpty('Không lấy được dữ liệu. Hãy thử lại.');}}

autoEl('automationNew').addEventListener('click',()=>autoRenderBuilder(autoDraftNew()));
let autoSearchTimer;
autoEl('automationSearch').addEventListener('input',()=>{clearTimeout(autoSearchTimer);
  autoSearchTimer=setTimeout(loadAutomationWorkspace,250);});
for(const id of ['automationState','automationTriggerFilter','automationLastRun'])
  autoEl(id).addEventListener('change',loadAutomationWorkspace);
autoEl('automationContent').addEventListener('change',event=>{
  if(event.target.id==='autoTemplate'&&event.target.value){const draft=autoTemplates[event.target.value];
    autoRenderBuilder({...structuredClone(draft),run_frequency:'manual',priority:'normal',is_enabled:false},autoState.editing);}
  else if(event.target.matches('[data-auto-field]')){const row=event.target.closest('[data-auto-condition]');
    const kind=autoFieldType(event.target.value);row.querySelector('[data-auto-operator]').innerHTML=
      autoOptions(autoFieldOps[kind],autoFieldOps[kind][0][0]);}
  else if(event.target.matches('[data-auto-action-type]')){const draft=autoReadDraft();
    const row=event.target.closest('[data-auto-action]');
    const index=[...row.parentNode.children].indexOf(row);
    if(draft.actions[index])draft.actions[index].value='';
    autoRenderBuilder(draft,autoState.editing);}
});
autoEl('automationContent').addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  const id=button.dataset.autoOpen||button.dataset.autoEdit||button.dataset.autoTest||
    button.dataset.autoRun||button.dataset.autoToggle||button.dataset.autoDuplicate||
    button.dataset.autoExport||button.dataset.autoDelete;
  try{
    if(button.hasAttribute('data-auto-back')){autoRenderList();return;}
    if(button.dataset.autoOpen){await autoShowDetail(id);return;}
    if(button.dataset.autoEdit){const rule=autoFind(id)||await autoJson('/api/automations/'+id);
      autoRenderBuilder({name:rule.name,description:rule.description,trigger_type:rule.trigger_type,
        run_frequency:rule.run_frequency,priority:rule.priority,is_enabled:rule.is_enabled,
        conditions:rule.conditions_json,actions:rule.actions_json},id);return;}
    if(button.hasAttribute('data-auto-add-group')){const draft=autoReadDraft();
      if(autoEl('autoGroups').children.length>=3)return toast('Tối đa 3 nhóm điều kiện.',true);
      autoEl('autoGroups').insertAdjacentHTML('beforeend',autoGroupMarkup({logic:'AND',items:[]}));return;}
    if(button.hasAttribute('data-auto-remove-group')){if(autoEl('autoGroups').children.length<=1)
      return toast('Cần giữ ít nhất một nhóm.',true);button.closest('[data-auto-group]').remove();return;}
    if(button.hasAttribute('data-auto-add-condition')){const list=button.closest('[data-auto-group]')
      .querySelector('[data-auto-condition-list]');if(list.children.length>=12)return toast('Mỗi nhóm tối đa 12 điều kiện.',true);
      list.insertAdjacentHTML('beforeend',autoConditionMarkup());return;}
    if(button.hasAttribute('data-auto-remove-condition')){button.closest('[data-auto-condition]').remove();return;}
    if(button.hasAttribute('data-auto-add-action')){const list=autoEl('autoActions');
      if(list.children.length>=8)return toast('Tối đa 8 hành động.',true);
      list.insertAdjacentHTML('beforeend',autoActionMarkup());return;}
    if(button.hasAttribute('data-auto-remove-action')){button.closest('[data-auto-action]').remove();return;}
    if(button.dataset.autoMove){const row=button.closest('[data-auto-action]');
      if(button.dataset.autoMove==='up'&&row.previousElementSibling)row.parentNode.insertBefore(row,row.previousElementSibling);
      if(button.dataset.autoMove==='down'&&row.nextElementSibling)row.parentNode.insertBefore(row.nextElementSibling,row);return;}
    if(button.hasAttribute('data-auto-preview')){button.disabled=true;autoStatus('Đang test rule…');
      try{autoRenderPreview(await autoJson('/api/automations/preview',{
        method:'POST',body:JSON.stringify(autoReadDraft())}));autoStatus('Test hoàn tất; chưa thực thi hành động.');}
      finally{button.disabled=false;}return;}
    if(button.hasAttribute('data-auto-save')){button.disabled=true;
      try{const path=autoState.editing?'/api/automations/'+autoState.editing:'/api/automations';
        const saved=await autoJson(path,{method:'POST',body:JSON.stringify(autoReadDraft())});
        toast('Đã lưu rule.');await loadAutomationWorkspace();await autoShowDetail(saved.id);}
      finally{button.disabled=false;}return;}
    if(button.dataset.autoTest){const result=await autoJson('/api/automations/'+id+'/test',
      {method:'POST',body:'{}'});if(autoState.view==='detail'){
        autoEl('autoDetailBody').innerHTML=`<div id="autoPreview"></div>`;autoRenderPreview(result);}
      else toast(`${result.matched_count}${result.truncated?'+':''} gói phù hợp; chưa thực thi.`);return;}
    if(button.dataset.autoRun){button.disabled=true;button.textContent='Đang chạy…';
      try{const result=await autoJson('/api/automations/'+id+'/run',{method:'POST',body:'{}'});
        toast(`Đã xử lý ${result.matched_count} gói · ${result.action_count} hành động.`);
        await loadAutomationWorkspace();await autoShowDetail(id,'runs');}finally{button.disabled=false;}return;}
    if(button.dataset.autoToggle){const rule=autoFind(id)||autoState.detail;
      await autoJson('/api/automations/'+id+'/'+(rule.is_enabled?'pause':'enable'),
        {method:'POST',body:'{}'});await loadAutomationWorkspace();
      if(autoState.detail?.id===id)await autoShowDetail(id);return;}
    if(button.dataset.autoDuplicate){const copy=await autoJson('/api/automations/'+id+'/duplicate',
      {method:'POST',body:'{}'});await loadAutomationWorkspace();await autoShowDetail(copy.id);return;}
    if(button.dataset.autoDelete){if(!confirm('Xóa rule này? Lịch sử chạy vẫn được giữ.'))return;
      await autoJson('/api/automations/'+id+'/delete',{method:'POST',body:'{}'});
      await loadAutomationWorkspace();toast('Đã xóa rule.');return;}
    if(button.dataset.autoExport){const rule=autoFind(id)||autoState.detail;
      const config={name:rule.name,description:rule.description,trigger_type:rule.trigger_type,
        conditions:rule.conditions_json,actions:rule.actions_json,
        run_frequency:rule.run_frequency,priority:rule.priority,is_enabled:false};
      await saveBlob(new Blob([JSON.stringify(config,null,2)],{type:'application/json'}),
        'automation-'+id+'.json');return;}
    if(button.dataset.autoTab){autoState.detailTab=button.dataset.autoTab;
      autoEl('automationContent').querySelectorAll('[data-auto-tab]').forEach(tab=>
        tab.classList.toggle('active',tab===button));await autoRenderDetailTab(button.dataset.autoTab);return;}
    if(button.dataset.autoEvents){const events=(await autoJson('/api/automations/runs/'+
      button.dataset.autoEvents+'/events')).items||[];
      autoEl('autoDetailBody').innerHTML=`<button type="button" class="btn ghost" data-auto-tab="runs">← Lượt chạy</button>
        <h3>Sự kiện</h3>${events.length?`<ul class="automation-run-list">${events.map(item=>
          `<li class="automation-run"><span>${esc(item.entity_id)} · ${esc(item.action)}</span>
          <span class="automation-badge ${item.status==='failed'?'error':''}">${esc(item.status)}</span></li>`).join('')}</ul>`:
          autoEmpty('Lượt chạy này không có hành động mới.')}`;return;}
  }catch(error){autoStatus(error.message,true);toast(error.message,true);}
});
if(document.body.dataset.view==='automations')void loadAutomationWorkspace();
