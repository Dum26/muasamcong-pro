const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const source=fs.readFileSync('web/automation.js','utf8');
const elements=new Map();
const element=id=>{if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',
  children:[],classList:{toggle(){}},querySelectorAll:()=>[]});return elements.get(id);};
const escape=value=>String(value??'').replace(/[&<>"']/g,char=>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const context=vm.createContext({document:{getElementById:element},esc:escape,
  api:async()=>({json:async()=>({})}),URLSearchParams,Date,Number,Math,Set,
  encodeURIComponent,structuredClone,Blob,console});
vm.runInContext(source.slice(0,source.indexOf("\nautoEl('automationNew')")),context);
vm.runInContext(`autoState.schema={fields:{text:['title','saved_search'],number:['package_price'],
  date:['bid_closing_date'],boolean:['is_followed']},triggers:{NEW_TENDER:'TBMT mới',
  NEW_DOCUMENT:'Tài liệu mới',SAVED_SEARCH_MATCH:'Khớp bộ lọc'}}`,context);

assert.equal(vm.runInContext("autoTemplates.document.trigger_type",context),'NEW_DOCUMENT');
assert.equal(vm.runInContext("autoTemplates.document.actions[0].type",context),'QUEUE_DOCUMENT_CHECK');
assert.equal(vm.runInContext("autoTemplates.saved.trigger_type",context),'SAVED_SEARCH_MATCH');
assert.match(vm.runInContext("autoConditionMarkup({field:'title',operator:'contains',value:'<script>'})",context),/&lt;script&gt;/);
assert.doesNotMatch(vm.runInContext("autoConditionMarkup({field:'title',operator:'contains',value:'<script>'})",context),/<script>/);
assert.deepEqual(Array.from(vm.runInContext("autoRuleStatus({last_run_error:'Lỗi',last_run_at:'2026-09-28',is_enabled:true})",context)),['Lỗi gần nhất','error']);
assert.deepEqual(Array.from(vm.runInContext("autoRuleStatus({last_run_error:null,last_run_at:null,is_enabled:false})",context)),['Chưa chạy','']);

vm.runInContext("autoRenderBuilder(autoTemplates.saved)",context);
assert.match(element('automationContent').innerHTML,/WHEN/);
assert.match(element('automationContent').innerHTML,/IF/);
assert.match(element('automationContent').innerHTML,/THEN/);
assert.match(element('automationContent').innerHTML,/Bộ lọc đã lưu/);
vm.runInContext("autoRenderPreview({matched_count:1,scanned_count:10,truncated:false,items:[{tender_code:'IB1',title:'<img src=x>'}]})",context);
assert.match(element('autoPreview').innerHTML,/\/app\/tenders\/IB1/);
assert.match(element('autoPreview').innerHTML,/&lt;img src=x&gt;/);
vm.runInContext("autoState.analytics={days:14,trend:[{day:'2026-09-28',runs:2,matches:4,failures:0}],actions:[{action:'FOLLOW_TENDER',count:3}]};autoRenderAnalytics()",context);
assert.match(element('automationAnalytics').innerHTML,/Hoạt động 14 ngày/);
assert.match(element('automationAnalytics').innerHTML,/Theo dõi gói · 3/);

for(const endpoint of ['/api/automations/preview',"'/test'","'/run'","'pause':'enable'"])
  assert.ok(source.includes(endpoint),`missing UI action ${endpoint}`);
for(const action of ['data-auto-save','data-auto-delete','data-auto-events','data-auto-toggle'])
  assert.ok(source.includes(action),`missing UI control ${action}`);
assert.ok(!source.includes('automationImport'));
assert.ok(!fs.readFileSync('web/index.html','utf8').includes('automationImport'));
console.log('PASS: automation templates, builder, safe preview, status and rule actions');
