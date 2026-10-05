const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: '', checked: false, disabled: false, textContent: '',
    classList: { toggle() {}, add() {}, remove() {} },
    querySelector(selector) { return element(id + selector); },
  });
  return elements.get(id);
}
const modes = [{value:'Thông báo mời thầu'}, {value:'Kế hoạch lựa chọn nhà thầu'}];
const context = vm.createContext({
  document: {getElementById:element, querySelectorAll:()=>modes}, console,
  localStorage: {getItem:()=>'{corrupted', setItem:()=>{throw Error('storage unavailable');}},
});
const source = fs.readFileSync('web/app.js','utf8');
vm.runInContext(source.slice(0,source.indexOf("$('searchForm').addEventListener")),context);
vm.runInContext(`
  toast=()=>{}; syncMode=()=>{};
  const now=Date.now();
  const vi=hours=>{const d=new Date(now+hours*3600000+7*3600000);return String(d.getUTCDate()).padStart(2,'0')+'/'+String(d.getUTCMonth()+1).padStart(2,'0')+'/'+d.getUTCFullYear()+' '+String(d.getUTCHours()).padStart(2,'0')+':'+String(d.getUTCMinutes()).padStart(2,'0');};
  state.rows=[
    {index:0,notify_no:'IB0',package_name:'Thuốc điều trị',location:'Hà Nội',tender_status:'Chưa đóng thầu',bid_close_date:vi(20)},
    {index:1,notify_no:'IB1',package_name:'Thuốc điều trị',location:'Hà Nội',tender_status:'Đã hủy TBMT',bid_close_date:vi(20)},
    {index:2,notify_no:'IB2',package_name:'Thuốc điều trị',location:'Huế',tender_status:'Chưa đóng thầu',bid_close_date:vi(50)},
    {index:3,notify_no:'IB3',package_name:'Thiết bị',location:'Hà Nội',tender_status:'Chưa đóng thầu',bid_close_date:vi(-1)},
    {index:4,notify_no:'IB4',package_name:'Thuốc điều trị',location:'Hà Nội',tender_status:'Chưa đóng thầu',bid_close_date:''},
  ];
  $('quickFilter').value='dieu thuoc ha noi'; $('viewStatus').value='Chưa đóng thầu';
  $('viewLocation').value='Hà Nội'; $('viewDeadline').value='24'; state.selected=new Set([0,2]); applyView();
  globalThis.matches=state.filtered.map(r=>r.index); globalThis.selected=[...state.selected];
  globalThis.cancelBadge=deadlineBadge(state.rows[1]); globalThis.missingBadge=deadlineBadge(state.rows[4]);
  globalThis.invalidDate=parseViDate('31/02/2026 12:00');
  globalThis.fixedZone=parseViDate('24/09/2026 07:00');
  clearViewFilters(); globalThis.cleared=state.filtered.length;
  restoreQuery({mode:'Kế hoạch lựa chọn nhà thầu',keyword:'thuoc',pages:20,use_dates:false,detail:true,fast_mode:false,remove_duplicates:false,date_from:'01/09/2026',date_to:'24/09/2026'});
  globalThis.restored=['useDates','detail','fastMode','removeDuplicates'].map(id=>$(id).checked);
  globalThis.restoredPages=$('pages').value;
  globalThis.corruptHistory=recentQueries();
  writeLocal('test','value');
`,context);
assert.deepEqual(Array.from(context.matches),[0]);
assert.deepEqual(Array.from(context.selected),[0]);
assert.equal(context.cancelBadge,'');
assert.equal(context.missingBadge,'');
assert.equal(context.invalidDate,0);
assert.equal(context.fixedZone,Date.parse('2026-09-24T00:00:00Z'));
assert.equal(context.cleared,5);
assert.deepEqual(Array.from(context.restored),[false,true,false,false]);
assert.equal(context.restoredPages,'20');
assert.equal(context.corruptHistory.length,0);
console.log('PASS: combined filters, accents, deadlines, timezone, selection, complete query restore, unavailable storage');

vm.runInContext(`
  state.filtered=[{notify_no:'IB3',lot_file_status:'done'},
    {notify_no:'IB1',lot_file_status:'Ko co file'},
    {notify_no:'IB2',lot_file_status:'Không kiểm tra (quét nhanh)'},
    {notify_no:'IB4',lot_file_status:'Chưa kiểm tra được'},
    {notify_no:'IB5',has_lots:true}];
  globalThis.fileColumn=resultColumnText('__lot_file');
  globalThis.codeColumn=resultColumnText('__code');
  render();
`,context);
assert.equal(context.fileColumn,'Có file\nKhông có file\nChưa kiểm tra\nLỗi kiểm tra\nCó file');
assert.equal(context.codeColumn,'IB3\nIB1\nIB2\nIB4\nIB5');
assert.equal((element('resultBody').innerHTML.match(/class="lot-availability"/g)||[]).length,5);
assert.ok(fs.readFileSync('web/index.html','utf8').includes('data-copy="__lot_file"'));
vm.runInContext("state.filtered=[{plan_no:'2600287943',plan_reference:'PL2600287943-02'}];globalThis.versionedCode=resultColumnText('__code')",context);
assert.equal(context.versionedCode,'PL2600287943');
vm.runInContext("state.rows=[{index:0,public_date:'13/09/2026'},{index:1,public_date:'11/09/2026'},{index:2,public_date:'12/09/2026 17:00'},{index:3,public_date:'01/10/2026'},{index:4,public_date:''}];$('sortBy').value='default';applyView();globalThis.oldestFirst=state.filtered.map(r=>r.index);$('sortBy').value='newest';applyView();globalThis.newestFirst=state.filtered.map(r=>r.index)",context);
assert.deepEqual(Array.from(context.oldestFirst),[1,2,0,3,4]);
assert.deepEqual(Array.from(context.newestFirst),[3,0,2,1,4]);
vm.runInContext("state.filtered=[{index:0,plan_no:'2600287943',package_name:'Gói thuốc',investor_name:'Bệnh viện A',source_url:'https://muasamcong.mpi.gov.vn/web/guest/contractor-selection?type=es-plan-project-p&id=ee8c8976-b9a3-43e8-a276-70eadb5d9380'}];render();globalThis.investorColumn=resultColumnText('investor_name');globalThis.linkedRow=$('resultBody').innerHTML",context);
assert.equal(context.investorColumn,'Bệnh viện A');
assert.ok(context.linkedRow.includes('class="package-name package-link"'));
assert.ok(context.linkedRow.includes('target="_blank"'));
assert.ok(context.linkedRow.includes('Bệnh viện A'));
vm.runInContext("state.sourceCount=91;state.rows=[{plan_no:'2600287943'}];renderStats();globalThis.portalCount=$('statTotal').textContent;globalThis.countHint=$('statTotalHint').textContent",context);
assert.equal(context.portalCount,91);
assert.ok(context.countHint.includes('1 dòng đã tải'));
vm.runInContext("state.mode='Kế hoạch lựa chọn nhà thầu';state.rows=[{lot_file_status:'done'},{lot_file_status:'Ko co file'},{lot_file_status:'Không kiểm tra (quét nhanh)'}];renderStats();globalThis.planMetrics=[$('statOpenLabel').textContent,$('statOpen').textContent,$('statReview').textContent,$('statResult').textContent]",context);
assert.deepEqual(Array.from(context.planMetrics),['Chưa đóng thầu',0,0,0]);
console.log('PASS: file availability labels, visible column, copy order and duplicate values');
vm.runInContext("copyText=async value=>{globalThis.copiedColumn=value};state.filtered=[{notify_no:'IB3'},{notify_no:'IB1'}];state.headerSort=null",context);
vm.runInContext("activateResultHeader({dataset:{copy:'__code'},textContent:'Mã TBMT / KHLCNT'})",context).then(()=>{
  assert.equal(context.copiedColumn,'IB3\nIB1');
  assert.equal(vm.runInContext('state.headerSort',context),null);
  vm.runInContext("state.rows=[{index:0,notify_no:'IB3'},{index:1,notify_no:'IB1'}];activateResultHeader({dataset:{copy:'__code'},textContent:'Mã TBMT / KHLCNT'},true)",context);
  assert.equal(vm.runInContext('state.headerSort.key',context),'__code');
  console.log('PASS: click copies the filtered column; Shift+click retains sorting');
}).catch(error=>{console.error(error);process.exitCode=1;});
