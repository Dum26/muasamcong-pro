const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: '', checked: false, disabled: false, textContent: '',
    classList: { toggle() {}, add() {}, remove() {} },
    setAttribute() {},
    querySelector() { return element(id + '/child'); },
    scrollIntoView() {}, appendChild() {},
  });
  return elements.get(id);
}
const context = vm.createContext({
  document: { getElementById: element }, console, setTimeout,
});
const source = fs.readFileSync('web/app.js', 'utf8');
vm.runInContext(source.slice(0, source.indexOf("$('searchForm').addEventListener")), context);

(async () => {
  await vm.runInContext(`(async () => {
    toast=()=>{}; saveBlob=async()=>{}; saveRecent=()=>{};
    state.rows=Array.from({length:649},(_,index)=>({index,notify_no:'IB2600'+String(index).padStart(6,'0'),public_date:index>=200&&index<286?'01/09/2026':'01/05/2026'}));
    state.jobId='september'; state.selected.add(0);
    $('quickFilter').value='/09/2026'; applyView();
    globalThis.filteredCount=state.filtered.length;
    globalThis.hiddenSelectionCount=state.selected.size;
    api=async(path, options)=>{
      globalThis.exportPayload=JSON.parse(options.body);
      return {blob:async()=>({}),headers:{get:()=>null}};
    };
    await download('/api/export',false,'result.xlsx');
  })()`, context);
  assert.equal(context.filteredCount, 86);
  assert.equal(context.hiddenSelectionCount, 0);
  assert.deepEqual(Array.from(context.exportPayload.indices), Array.from({length:86}, (_,i)=>i+200));

  await vm.runInContext(`(async()=>{
    api=async(path,options)=>{
      if(path==='/api/extract') {
        const indices=JSON.parse(options.body).indices;
        return {json:async()=>({id:'new-86',state:'done',rows:indices.map(index=>({code:state.rows[index].notify_no,tender_status:'Review',location:'Ha Noi',bid_form:'Open bidding',below_value:'WRONG_NEXT_CODE'}))})};
      }
      globalThis.codesPayload=JSON.parse(options.body);
      if(path==='/api/lots')return {json:async()=>({files:[],issues:[]})};
      return {blob:async()=>({}),headers:{get:()=>null}};
    };
    await extractFromResults();
    globalThis.extractionCount=state.extracted.length;
    globalThis.extractionHtml=$('extractBody').innerHTML;
    globalThis.resultHtml=$('resultBody').innerHTML;
    globalThis.paginationState=$('paginationSummary').textContent;
    globalThis.copiedColumns={
      stt:extractedColumnText('__stt'),code:extractedColumnText('code'),
      status:extractedColumnText('tender_status'),location:extractedColumnText('location'),
      bidForm:extractedColumnText('bid_form')
    };
    copyText=async text=>{globalThis.actualCopiedText=text;};
    await copyExtractedColumn('location','Địa điểm');
    selectAllExtracted(true);
    globalThis.allSelected=extractedSelectionIndices().length;
    await downloadExtractedLots();
    globalThis.lotPayload=globalThis.codesPayload;
    state.extractedSelected.delete(200); // Outside this extraction does not affect selection.
    state.extractedSelected.delete(0);
    globalThis.partialSelected=extractedSelectionIndices().length;
    await exportExtraction();
    $('quickFilter').value='no matches'; applyView();
    globalThis.cleared=[state.extractionId,state.extracted.length,$('exportExtracted').disabled];
  })()`,context);
  assert.equal(context.extractionCount,86);
  assert.equal((context.extractionHtml.match(/<tr>/g)||[]).length,86);
  assert.equal((context.resultHtml.match(/<tr /g)||[]).length,50);
  assert.equal(context.paginationState,'Trang 1 / 2');
  assert.ok(context.extractionHtml.includes('Ha Noi'));
  assert.ok(context.extractionHtml.includes('Open bidding'));
  assert.ok(!context.extractionHtml.includes('WRONG_NEXT_CODE'));
  assert.equal(context.copiedColumns.stt.split('\n').length,86);
  assert.equal(context.copiedColumns.stt.split('\n').at(-1),'86');
  assert.equal(context.copiedColumns.code.split('\n')[0],'IB2600000200');
  assert.equal(context.copiedColumns.status.split('\n')[0],'Review');
  assert.equal(context.copiedColumns.location.split('\n').length,86);
  assert.equal(context.copiedColumns.bidForm.split('\n')[0],'Open bidding');
  assert.equal(context.actualCopiedText,context.copiedColumns.location);
  assert.equal(context.allSelected,86);
  assert.equal(context.partialSelected,85);
  assert.equal(context.lotPayload.extraction_id,'new-86');
  assert.deepEqual(Array.from(context.lotPayload.indices),Array.from({length:86},(_,i)=>i));
  assert.equal(context.codesPayload.extraction_id,'new-86');
  assert.equal(context.codesPayload.expected_count,86);
  assert.deepEqual(Array.from(context.cleared),[null,0,true]);

  await vm.runInContext(`(async()=>{
    api=async()=>({json:()=>new Promise(resolve=>globalThis.finishOldExtraction=resolve)});
    const pending=submitExtraction({text:'old'},'results');
    await Promise.resolve();
    clearExtraction();
    finishOldExtraction({id:'old-649',rows:Array(649).fill({code:'IB1'})});
    await pending;
    globalThis.staleIgnored=state.extractionId===null&&state.extracted.length===0;

    state.extractionId='old-649';state.extracted=Array(649).fill({code:'IB1'});
    searchParams=()=>({mode:'Thông báo mời thầu',use_dates:true});
    api=async()=>{throw new Error('search failed');};
    await startSearch();
    globalThis.failedSearchCleared=state.jobId===null&&state.extractionId===null&&state.extracted.length===0;
  })()`,context);
  assert.equal(context.staleIgnored,true);
  assert.equal(context.failedSearchCleared,true);
  await vm.runInContext(`(async()=>{
    state.filtered=[{index:0,plan_no:'2600301140',plan_name:'Kế hoạch A'}];
    state.jobId='plans';
    api=async(path,options)=>{
      globalThis.planApiPath=path;
      globalThis.planExtractPayload=JSON.parse(options.body);
      return {json:async()=>({id:'plan-list',state:'done',rows:[{code:'PL2600301140',code_type:'KHLCNT',title:'Kế hoạch A'}]})};
    };
    await extractFromResults();
    selectAllExtracted(true);
    globalThis.planLotDisabled=$('downloadExtractedLots').disabled;
    globalThis.planTypeColumn=extractedColumnText('code_type');
    globalThis.planTable=$('extractBody').innerHTML;
  })()`,context);
  assert.equal(context.planApiPath,'/api/extract');
  assert.deepEqual(Array.from(context.planExtractPayload.indices),[0]);
  assert.equal(context.planLotDisabled,true);
  assert.equal(context.planTypeColumn,'KHLCNT');
  assert.match(context.planTable,/Kế hoạch A/);
  console.log('PASS: 86/649 filtered export, extraction count, hidden selections, stale results and failed search');
})().catch(error=>{console.error(error);process.exitCode=1;});
