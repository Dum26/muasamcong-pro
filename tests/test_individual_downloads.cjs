const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
function element(id) {
  if(!elements.has(id))elements.set(id,{value:'',textContent:'',disabled:false,classList:{toggle(){}},scrollIntoView(){},querySelector(){return element(id+'/child');}});
  return elements.get(id);
}
const context = vm.createContext({document:{getElementById:element},console,setTimeout});
const source = fs.readFileSync('web/app.js','utf8');
vm.runInContext(source.slice(0,source.indexOf("$('searchForm').addEventListener")),context);
(async()=>{
  await vm.runInContext(`(async()=>{
    toast=()=>{};renderExtraction=()=>{};
    globalThis.saved=[]; saveBlob=async(blob,name)=>{saved.push(name);return 'folder';};
    api=async(path,options)=>{
      if(path==='/api/lots')return {json:async()=>({files:[1,2,3].map(i=>({name:'BP'+i+'.xlsx',code:'BP'+i,url:'/file/'+i})),issues:[{code:'BP4',reason:'Missing'}]})};
      if(path==='/file/2')throw Error('Disconnected');
      return {blob:async()=>({})};
    };
    await downloadLotSelection({job_id:'job',indices:[0,1,2]},3);
    globalThis.fileStates=state.lotFiles.map(file=>file.status||file.error);
    globalThis.links=$('lotFileList').innerHTML;
    globalThis.issues=$('lotIssueList').innerHTML;
    globalThis.finished=!state.lotsLoading&&!$('saveAllLotFiles').disabled;
  })()`,context);
  assert.deepEqual(Array.from(context.saved),['BP1.xlsx','BP3.xlsx']);
  assert.equal(context.fileStates[1],'Disconnected');
  assert.equal((context.links.match(/<a /g)||[]).length,3);
  assert.ok(context.issues.includes('BP4'));
  assert.equal(context.finished,true);
  vm.runInContext(source.slice(source.indexOf('async function saveBlob('),source.indexOf('function responseFilename(')),context);
  await vm.runInContext(`(async()=>{
    state.directory={name:'Output',getFileHandle:async(name,options)=>{
      if(options?.create){globalThis.createdName=name;return {createWritable:async()=>({write:async()=>{},close:async()=>{}})};}
      if(name==='BP1.xlsx')return {};
      const error=new Error('not found');error.name='NotFoundError';throw error;
    }};
    await saveBlob({},'BP1.xlsx');
  })()`,context);
  assert.equal(context.createdName,'BP1 (2).xlsx');
  console.log('PASS: separate saves, individual retry links, partial failure continues, errors stay visible');
})().catch(error=>{console.error(error);process.exitCode=1;});
