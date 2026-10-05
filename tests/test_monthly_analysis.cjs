const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const elements=new Map();
const get=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',innerHTML:'',classList:{toggle(){},remove(){},add(){}},scrollIntoView(){}});return elements.get(id);};
const context=vm.createContext({document:{getElementById:get},console});
const app=fs.readFileSync('web/app.js','utf8');
vm.runInContext(app.slice(0,app.indexOf("$('searchForm').addEventListener")),context);
const analysis=fs.readFileSync('web/analysis.js','utf8');
vm.runInContext(analysis.slice(0,analysis.indexOf("$('monthlyAnalysis').addEventListener")),context);
vm.runInContext(`
  const sample=[
    {public_date:'01/09/2026',package_name:'Thuốc generic',location:'Hà Nội',winner:'Công ty A; Công ty B; công ty a'},
    {public_date:'30/09/2026 23:59',package_name:'Thuốc generic',location:'Hà Nội',winner:'Công ty A'},
    {public_date:'01/10/2026',package_name:'Thiết bị y tế',location:'Huế'},
    {public_date:'31/09/2026',package_name:'Thuốc generic'},
    {public_date:'',package_name:'Biệt dược'},
  ];
  globalThis.report=monthlyReport(sample,'2026-09');
  globalThis.generic=monthlyReport(sample,'','generic');
  globalThis.empty=monthlyReport(sample,'2025-01');
  globalThis.invalid=reportMonth(sample[3]);
  globalThis.days=reportDailyTrend(sample,'2026-09');
  state.rows=sample;state.filtered=[sample[2]];
  renderMonthlyAnalysis();
  globalThis.total=$('reportTotal').textContent;
  $('reportScope').value='filtered';renderMonthlyAnalysis();
  globalThis.filteredTotal=$('reportTotal').textContent;
  reportBars('safe',[{label:'<img src=x>',count:1}],1);
`,context);
assert.equal(context.report.rows.length,2);
assert.equal(context.report.knownWinners,2);
assert.equal(context.report.winners[0].count,2);
assert.equal(context.report.winners[1].count,1);
vm.runInContext(`
  globalThis.investorReport=monthlyReport([
    {index:0,plan_no:'100',public_date:'11/09/2026',investor_name:'Hospital A'},
    {index:1,plan_no:'101',public_date:'12/09/2026',investor_name:'Hospital A'},
    {index:2,plan_no:'102',public_date:'13/09/2026',investor_name:'Hospital B'},
    {index:3,plan_no:'103',public_date:'14/09/2026',investor_name:''},
  ],'2026-09');
`,context);
assert.equal(context.investorReport.knownInvestors,3);
assert.equal(context.investorReport.investors[0].label,'Hospital A');
assert.equal(context.investorReport.investors[0].count,2);
assert.equal(context.report.locations[0].count,2);
assert.equal(context.report.unknownDates,2);
assert.deepEqual(Array.from(context.report.trend,x=>x.label),['2026-09','2026-10']);
assert.equal(context.generic.rows.length,3);
assert.equal(context.empty.rows.length,0);
assert.equal(context.invalid,'');
assert.equal(context.days.length,30);
assert.equal(context.days[0].count,1);
assert.equal(context.days[29].count,1);
assert.equal(context.days[1].count,0);
assert.equal(context.total,5);
assert.equal(context.filteredTotal,1);
assert.ok(get('safe').innerHTML.includes('&lt;img src=x&gt;'));
vm.runInContext("reportBars('percent',[{label:'A',count:1},{label:'B',count:1}],4,10,'percent')",context);
assert.ok(get('percent').innerHTML.includes('25%'));
vm.runInContext("$('reportScope').value='all';renderMonthlyAnalysis()",context);
assert.ok(get('reportLocations').innerHTML.includes('xy-column-chart'));
assert.ok(!fs.readFileSync('web/index.html','utf8').includes('id="reportGroups"'));
assert.ok(get('reportLocations').innerHTML.includes('rotate(-45'));
assert.ok(get('reportLocations').innerHTML.includes('data-chart-id="reportLocations"'));
assert.ok(get('reportFocusChart').innerHTML.includes('trend-line'));
assert.ok(get('reportFocusChart').innerHTML.includes('Ngày đăng tải')===false);
vm.runInContext("$('reportScope').value='all';$('reportMonth').value='2026-09';$('reportDimension').value='locations';$('reportMeasure').value='count';$('reportTop').value='10';renderMonthlyAnalysis()",context);
assert.ok(get('reportFocusChart').innerHTML.includes('Ngày đăng tải'));
assert.ok((get('reportFocusChart').innerHTML.match(/class="trend-dot"/g)||[]).length>=30);
vm.runInContext("$('reportMeasure').value='percent';renderMonthlyAnalysis()",context);
assert.ok(get('reportFocusChart').innerHTML.includes('100%'));
vm.runInContext(`
  state.mode='Kế hoạch lựa chọn nhà thầu';
  state.rows=[
    {index:0,plan_reference:'PL2600000001-00',plan_name:'Thuốc generic',location:'Hà Nội',public_date:'11/09/2026'},
    {index:1,plan_reference:'PL2600000002-00',plan_name:'Thuốc generic',location:'Hà Nội',public_date:'12/09/2026'},
    {index:2,plan_reference:'PL2600000003-00',plan_name:'Thiết bị y tế',location:'Huế',public_date:'12/09/2026'},
  ];
  state.filtered=state.rows;
  $('reportMonth').value='';$('reportDimension').value='total';$('reportMeasure').value='count';
  renderMonthlyAnalysis();
  showBarCodes({dataset:{chartId:'reportLocations',chartIndex:'0'}});
  globalThis.selectedCodes=state.reportSelectedRows.map(reportCode);
`,context);
assert.deepEqual(Array.from(context.selectedCodes),['PL2600000001','PL2600000002']);
assert.ok(get('chartSelectionList').innerHTML.includes('PL2600000001'));
assert.ok(!get('chartSelectionList').innerHTML.includes('PL2600000003'));
assert.ok(get('reportStatuses').innerHTML.includes('Chưa có trạng thái đấu thầu'));
assert.ok(get('reportForms').innerHTML.includes('Chưa có hình thức LCNT'));
assert.ok(!analysis.includes('/api/lots'));
vm.runInContext(`
  state.rows=[
    {index:0,plan_no:'100',public_date:'11/09/2026',investor_name:'Hospital A'},
    {index:1,plan_no:'101',public_date:'12/09/2026',investor_name:'Hospital A'},
    {index:2,plan_no:'102',public_date:'13/09/2026',investor_name:'Hospital B'},
  ];
  state.filtered=state.rows;
  $('reportScope').value='all';$('reportMonth').value='';$('reportKeyword').value='';
  renderMonthlyAnalysis();
  showBarCodes({dataset:{chartId:'reportInvestorChart',chartIndex:'0'}});
  globalThis.investorCodes=state.reportSelectedRows.map(reportCode);
  globalThis.investorNote=$('reportInvestorNote').textContent;
`,context);
assert.deepEqual(Array.from(context.investorCodes),['PL100','PL101']);
assert.ok(context.investorNote.includes('toàn bộ 3 kết quả'));
assert.ok(!context.investorNote.includes('0 kết quả chưa có tên'));
console.log('PASS: monthly charts, safe labels, bar drilldown to matching codes, unavailable plan fields');
