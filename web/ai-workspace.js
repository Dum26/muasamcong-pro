/* Document workflow. AI calls occur only after a deliberate user action. */
const aiState={documents:[],page:1,hasMore:false,selectedId:'',viewerId:'',contentPage:1,
  contentMore:false,tab:'summary',analysis:null,analysisDocumentId:'',relatedId:'',busy:false,loaded:false};
const aiEl=id=>document.getElementById(id);
const aiEsc=value=>esc(String(value??''));
const aiIcons=()=>window.lucide?.createIcons();
const aiSize=size=>size<1024*1024?`${(size/1024).toFixed(1)} KB`:`${(size/1024/1024).toFixed(1)} MB`;
const aiStatus={uploaded:'Chờ đọc nội dung',extracting:'Đang xử lý',ready:'Sẵn sàng',failed:'Lỗi trích xuất'};

async function aiRequest(path,options={}){
  const response=await fetch(path,{credentials:'same-origin',...options,
    headers:options.body?{'Content-Type':'application/json',...(options.headers||{})}:options.headers});
  const data=await response.json();
  if(!response.ok)throw new Error(data.error||'Không thể xử lý yêu cầu.');
  return data;
}

async function loadAiWorkspace(){
  if(!aiState.loaded){aiState.loaded=true;await loadAiConfig();}
  await loadAiDocuments();
}
async function loadAiConfig(){
  try{const data=await aiRequest('/api/ai/config');aiState.config=data;
    aiEl('aiMaxUpload').textContent=`${data.max_upload_mb} MB`;
    aiEl('aiConfigBadge').textContent=data.configured?`Sẵn sàng · ${data.model}`:'AI chưa cấu hình';
    aiEl('aiConfigStatus').textContent=data.configured?`AI sử dụng ${data.provider} / ${data.model}. Chỉ gửi các đoạn chứng cứ liên quan khi bạn bấm Phân tích.`:'AI chưa được cấu hình. Bạn vẫn có thể tải lên, đọc và tải lại tài liệu; phân tích AI sẽ khả dụng sau khi quản trị cấu hình provider.';
    updateAiActions();
  }catch(error){aiState.config={configured:false,max_upload_mb:10,inline_extract_mb:3};aiEl('aiConfigBadge').textContent='Không lấy được cấu hình';aiEl('aiConfigStatus').textContent=error.message;}
}

async function loadAiDocuments(){
  aiEl('aiDocumentList').innerHTML='<p class="ai-empty">Đang tải tài liệu…</p>';
  try{const data=await aiRequest(`/api/documents?page=${aiState.page}`);
    aiState.documents=data.items||[];aiState.hasMore=!!data.has_more;
    aiEl('aiDocumentCount').textContent=String(aiState.documents.length)+(aiState.hasMore?'+':'');
    aiEl('aiPageLabel').textContent=`Trang ${aiState.page}`;
    aiEl('aiPrevPage').disabled=aiState.page<=1;aiEl('aiNextPage').disabled=!aiState.hasMore;
    renderAiDocuments();
    if(aiState.selectedId){const item=aiState.documents.find(doc=>doc.id===aiState.selectedId);if(item)refreshAiDocument(item);}
    updateAiActions();
  }catch(error){aiEl('aiDocumentList').innerHTML=`<p class="ai-error">${aiEsc(error.message)}</p><button class="btn ghost" id="aiRetryList" type="button">Thử lại</button>`;}
}

function renderAiDocuments(){
  aiEl('aiDocumentList').innerHTML=aiState.documents.length?aiState.documents.map(doc=>{
    const type=doc.filename.split('.').pop().toUpperCase(),active=doc.id===aiState.selectedId;
    return `<button class="ai-document-card ${active?'active':''}" type="button" data-ai-document="${doc.id}" aria-current="${active?'true':'false'}"><span class="ai-file-icon"><i data-lucide="file-text" aria-hidden="true"></i></span><span class="ai-file-info"><strong title="${aiEsc(doc.filename)}">${aiEsc(doc.filename)}</strong><small>${aiEsc(type)} · ${aiSize(doc.size)} · ${aiEsc(doc.created_at?.slice(0,16).replace('T',' ')||'')}</small>${doc.tender_code?`<small>Gói ${aiEsc(doc.tender_code)}</small>`:''}<span class="ai-file-status ${aiEsc(doc.status)}">${aiEsc(aiStatus[doc.status]||doc.status)}</span></span></button>`;
  }).join(''):'<p class="ai-empty">Chưa có tài liệu. Tải một hồ sơ lên để bắt đầu.</p>';
  const compare=aiEl('aiCompareDocument');const previous=compare.value;
  compare.innerHTML='<option value="">Chọn tài liệu để so sánh</option>'+aiState.documents.filter(doc=>doc.id!==aiState.selectedId&&doc.status==='ready').map(doc=>`<option value="${doc.id}">${aiEsc(doc.filename)}</option>`).join('');
  if([...compare.options].some(option=>option.value===previous))compare.value=previous;
  aiIcons();
}

function refreshAiDocument(doc){
  aiEl('aiDocumentTitle').textContent=doc.filename;
  aiEl('aiDocumentMeta').textContent=`${aiSize(doc.size)} · ${aiStatus[doc.status]||doc.status}${doc.tender_code?' · '+doc.tender_code:''}`;
  aiEl('aiTenderCode').value=doc.tender_code||'';
  aiEl('aiDownloadDocument').href=`/api/documents/${doc.id}/download`;
  aiEl('aiDownloadDocument').classList.remove('hidden');
  aiEl('aiProcessDocument').hidden=!['uploaded','failed','ready'].includes(doc.status);
  aiEl('aiOcrDocument').hidden=!doc.scan_likely;
  aiEl('aiLinkDocument').hidden=false;
  aiEl('aiDeleteDocument').hidden=false;
  aiEl('aiViewerStatus').textContent=doc.scan_likely?'PDF này có thể là bản scan. Chức năng OCR chưa được cấu hình.':doc.error||'Chọn đoạn văn bản để kiểm tra nguồn dẫn.';
  updateAiActions();
}

async function selectAiDocument(id){
  let doc=aiState.documents.find(item=>item.id===id);
  if(!doc){try{const data=await aiRequest(`/api/documents/${id}`);doc=data.document;if(doc){aiState.documents=[doc,...aiState.documents];}}catch(error){aiEl('aiViewerStatus').textContent=error.message;return;}}
  if(!doc)return;
  aiState.selectedId=id;aiState.viewerId=id;aiState.analysis=null;aiState.analysisDocumentId='';
  aiEl('aiAnalysisResult').innerHTML='';aiEl('aiAnalysisStatus').textContent='Chọn thao tác phân tích khi tài liệu đã sẵn sàng.';
  renderAiDocuments();refreshAiDocument(doc);
  await Promise.all([loadAiContent(id,1),loadAiHistory(id)]);
}

async function loadAiContent(id,page=1,append=false){
  if(!append)aiEl('aiDocumentContent').innerHTML='<p class="ai-empty">Đang đọc nội dung…</p>';
  try{const data=await aiRequest(`/api/documents/${id}/content?page=${page}`);
    aiState.viewerId=id;aiState.contentPage=page;aiState.contentMore=data.has_more;
    const markup=data.chunks.length?data.chunks.map(chunk=>`<article class="ai-source-block" id="ai-source-${chunk.source_id}"><div><span>${aiEsc(chunk.label)}</span><button type="button" data-ai-copy-source="${chunk.source_id}" aria-label="Sao chép đoạn ${aiEsc(chunk.label)}"><i data-lucide="copy" aria-hidden="true"></i></button></div><p>${aiEsc(chunk.text)}</p></article>`).join(''):'<p class="ai-empty">Chưa có văn bản trích xuất. PDF scan cần OCR riêng.</p>';
    if(append)aiEl('aiDocumentContent').insertAdjacentHTML('beforeend',markup);else aiEl('aiDocumentContent').innerHTML=markup;
    aiEl('aiMoreContent').hidden=!data.has_more;
    aiIcons();
  }catch(error){aiEl('aiDocumentContent').innerHTML=`<p class="ai-error">${aiEsc(error.message)}</p>`;}
}

async function loadAiHistory(id){
  try{const data=await aiRequest(`/api/documents/${id}/analyses`);
    aiEl('aiHistoryList').innerHTML=data.items.length?data.items.map(item=>`<button class="ai-history-item" type="button" data-ai-history="${item.id}"><strong>${aiEsc(item.analysis_type)}</strong><small>${aiEsc(item.created_at?.slice(0,16).replace('T',' ')||'')} · ${aiEsc(item.model)}</small></button>`).join(''):'<p>Chưa có phân tích.</p>';
    aiState.history=data.items;
  }catch(error){aiEl('aiHistoryList').textContent=error.message;}
}

function chooseAiTab(tab){
  aiState.tab=tab;
  document.querySelectorAll('[data-ai-tab]').forEach(button=>button.setAttribute('aria-selected',String(button.dataset.aiTab===tab)));
  aiEl('aiQuestionField').classList.toggle('hidden',tab!=='qa');
  aiEl('aiCompareField').classList.toggle('hidden',tab!=='compare');
  aiEl('aiOperation').closest('label').classList.toggle('hidden',['qa','compare'].includes(tab));
  const operations={summary:'summary',catalog:'catalog',requirements:'capacity',timeline:'timeline'};
  if(operations[tab])aiEl('aiOperation').value=operations[tab];
  updateAiActions();
}
function updateAiActions(){
  const doc=aiState.documents.find(item=>item.id===aiState.selectedId);
  const available=!!aiState.config?.configured&&doc?.status==='ready';
  aiEl('aiRunAnalysis').disabled=!available||aiState.busy;
  aiEl('aiRefreshAnalysis').disabled=!available||aiState.busy;
}

function sourceButtons(citations){return (citations||[]).map(source=>`<button class="ai-citation" type="button" data-ai-citation="${aiEsc(source.source_id)}">${aiEsc(source.label)}</button>`).join('');}
function renderAiAnalysis(item){
  aiState.analysis=item;aiState.analysisDocumentId=aiState.selectedId;
  aiState.relatedId=item.result?.compare_document_id||'';
  const result=item.result||{};
  let markup=result.answer?`<section class="ai-answer"><h4>Kết quả</h4><p>${aiEsc(result.answer)}</p><div class="ai-citations">${sourceButtons(result.citations)}</div></section>`:'';
  markup+=(result.sections||[]).map(section=>`<section class="ai-result-section"><h4>${aiEsc(section.title)}</h4>${(section.items||[]).map(entry=>`<div class="ai-fact"><strong>${aiEsc(entry.label)}</strong><p>${aiEsc(entry.value)}</p><div class="ai-citations">${sourceButtons(entry.citations)}</div></div>`).join('')}</section>`).join('');
  if(result.table?.length)markup+=`<section class="ai-result-section"><h4>Danh mục (${result.table.length})</h4><div class="ai-table-scroll"><table><thead><tr><th>STT</th><th>Hàng hóa/dịch vụ</th><th>Đơn vị</th><th>SL</th><th>Kỹ thuật</th><th>Xuất xứ</th><th>Giao hàng</th><th>Nguồn</th></tr></thead><tbody>${result.table.map((row,index)=>`<tr><td>${index+1}</td><td>${aiEsc(row.item)}</td><td>${aiEsc(row.unit)}</td><td>${aiEsc(row.quantity)}</td><td>${aiEsc(row.technical)}</td><td>${aiEsc(row.origin)}</td><td>${aiEsc(row.delivery)}</td><td>${sourceButtons(row.citations)}</td></tr>`).join('')}</tbody></table></div></section>`;
  if(result.comparison?.length)markup+=`<section class="ai-result-section"><h4>Đối chiếu (${result.comparison.length} tiêu chí)</h4><div class="ai-table-scroll"><table><thead><tr><th>Tiêu chí</th><th>Hồ sơ A</th><th>Hồ sơ B</th><th>Thay đổi</th></tr></thead><tbody>${result.comparison.map(row=>`<tr><td>${aiEsc(row.criterion)}</td><td>${aiEsc(row.value_a)}<br>${sourceButtons(row.citations_a)}</td><td>${aiEsc(row.value_b)}<br>${sourceButtons(row.citations_b)}</td><td>${aiEsc(row.change)}</td></tr>`).join('')}</tbody></table></div></section>`;
  aiEl('aiAnalysisResult').innerHTML=markup||'<p class="ai-empty">Không tìm thấy thông tin trong các đoạn đã phân tích.</p>';
  aiEl('aiAnalysisStatus').textContent=`${item.cached?'Đã mở kết quả đã lưu':'Phân tích hoàn tất'} · ${item.model} · ${item.created_at?.slice(0,16).replace('T',' ')||''}`;
  for(const id of ['aiExportXlsx','aiExportDocx','aiCopyResult'])aiEl(id).hidden=false;
}

async function runAiAnalysis(refresh=false){
  const doc=aiState.documents.find(item=>item.id===aiState.selectedId);if(!doc)return;
  const operation=aiState.tab==='qa'?'qa':aiState.tab==='compare'?aiEl('aiCompareMode').value:aiEl('aiOperation').value;
  const question=aiState.tab==='qa'?aiEl('aiQuestion').value.trim():'';
  const related=aiState.tab==='compare'?aiEl('aiCompareDocument').value:'';
  if(operation==='qa'&&!question){aiEl('aiAnalysisStatus').textContent='Hãy nhập câu hỏi.';aiEl('aiQuestion').focus();return;}
  if(operation==='compare'&&!related){aiEl('aiAnalysisStatus').textContent='Hãy chọn tài liệu thứ hai.';return;}
  aiState.busy=true;updateAiActions();aiEl('aiAnalysisStatus').textContent='Đang phân tích các đoạn chứng cứ liên quan…';
  aiEl('aiAnalysisResult').innerHTML='';aiState.analysis=null;
  for(const id of ['aiExportXlsx','aiExportDocx','aiCopyResult'])aiEl(id).hidden=true;
  try{const item=await aiRequest('/api/ai/analyze',{method:'POST',body:JSON.stringify({document_id:doc.id,operation,question,related_document_id:related,refresh})});
    renderAiAnalysis(item);await loadAiHistory(doc.id);
  }catch(error){aiEl('aiAnalysisStatus').textContent=error.message;}
  finally{aiState.busy=false;updateAiActions();}
}

async function aiUpload(file){
  if(!file)return;
  if(!aiState.config){await loadAiConfig();}
  if(file.size>aiState.config.max_upload_mb*1024*1024){aiEl('aiUploadStatus').textContent='File vượt giới hạn dung lượng.';return;}
  aiEl('aiUploadStatus').textContent='Đang đọc file…';
  const reader=new FileReader();
  reader.onerror=()=>{aiEl('aiUploadStatus').textContent='Không đọc được file trên máy.';};
  reader.onload=()=>{
    const encoded=String(reader.result).split(',',2)[1];
    const xhr=new XMLHttpRequest();xhr.open('POST','/api/documents/upload');xhr.setRequestHeader('Content-Type','application/json');
    aiEl('aiUploadProgress').hidden=false;aiEl('aiUploadProgress').value=0;
    xhr.upload.onprogress=event=>{if(event.lengthComputable){aiEl('aiUploadProgress').value=Math.round(event.loaded/event.total*100);aiEl('aiUploadStatus').textContent=`Đang tải ${aiEl('aiUploadProgress').value}%…`;}};
    xhr.onload=async()=>{aiEl('aiUploadProgress').hidden=true;let data={};try{data=JSON.parse(xhr.responseText);}catch{}
      if(xhr.status!==201){aiEl('aiUploadStatus').textContent=data.error||'Tải file thất bại.';return;}
      aiEl('aiUploadStatus').textContent='Đã tải lên. Đang đọc nội dung…';aiState.page=1;
      await loadAiDocuments();await selectAiDocument(data.document.id);
      if(file.size>aiState.config.inline_extract_mb*1024*1024){aiEl('aiUploadStatus').textContent='File đã tải lên và đang chờ job trích xuất. Trang sẽ tự cập nhật trạng thái.';return;}
      try{const processed=await aiRequest(`/api/documents/${data.document.id}/process`,{method:'POST',body:'{}'});
        aiEl('aiUploadStatus').textContent=processed.document.scan_likely?'Đã đọc file; PDF có thể là bản scan.':'Đã đọc nội dung tài liệu.';
        await loadAiDocuments();await selectAiDocument(data.document.id);
      }catch(error){aiEl('aiUploadStatus').textContent=`Không trích xuất được: ${error.message}`;await loadAiDocuments();}
    };
    xhr.onerror=()=>{aiEl('aiUploadProgress').hidden=true;aiEl('aiUploadStatus').textContent='Mất kết nối khi tải file.';};
    xhr.send(JSON.stringify({filename:file.name,mime_type:file.type||'application/octet-stream',
      tender_code:aiEl('aiTenderCode').value.trim(),data:encoded}));
  };
  reader.readAsDataURL(file);
}

async function jumpAiCitation(sourceId){
  let id=aiState.analysisDocumentId,source=sourceId;
  if(sourceId.startsWith('B:')){id=aiState.relatedId;source=sourceId.slice(2);}else if(sourceId.startsWith('A:'))source=sourceId.slice(2);
  if(!id)return;
  const number=Number(source.slice(1));const page=Math.max(1,Math.ceil(number/80));
  if(id!==aiState.viewerId||page!==aiState.contentPage)await loadAiContent(id,page);
  const doc=aiState.documents.find(item=>item.id===id);if(doc){aiEl('aiDocumentTitle').textContent=doc.filename;aiEl('aiDocumentMeta').textContent=`Nguồn ${sourceId} · ${doc.tender_code||'Tài liệu riêng'}`;}
  const target=document.getElementById(`ai-source-${source}`);if(target){target.scrollIntoView({behavior:'smooth',block:'center'});target.classList.add('ai-highlight');setTimeout(()=>target.classList.remove('ai-highlight'),1800);}
}

async function exportAi(format){
  if(!aiState.analysis)return;
  try{const response=await fetch('/api/ai/export',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({analysis_id:aiState.analysis.id,format})});
    if(!response.ok){const data=await response.json();throw new Error(data.error||'Xuất file thất bại.');}
    await saveBlob(await response.blob(),`Phan_tich_${aiState.analysis.id.slice(0,8)}.${format}`);
  }catch(error){aiEl('aiAnalysisStatus').textContent=error.message;}
}

async function renderAiTenderDocuments(code){
  const container=aiEl('detailAiDocuments');if(!container)return;
  try{const data=await aiRequest(`/api/documents?tender_code=${encodeURIComponent(code)}`);
    if(aiEl('detailAiDocuments')!==container)return;
    container.innerHTML=data.items.length?data.items.map(doc=>`<button class="ai-tender-document" type="button" data-ai-tender-document="${doc.id}">${aiEsc(doc.filename)} · ${aiEsc(aiStatus[doc.status]||doc.status)}</button>`).join(''):'Chưa có hồ sơ liên kết với mã này.';
  }catch{container.textContent='Không lấy được danh sách tài liệu.';}
}

aiEl('aiFileInput').addEventListener('change',event=>{void aiUpload(event.target.files[0]);event.target.value='';});
aiEl('aiDropZone').addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();aiEl('aiFileInput').click();}});
aiEl('aiDropZone').addEventListener('dragover',event=>{event.preventDefault();event.currentTarget.classList.add('dragging');});
aiEl('aiDropZone').addEventListener('dragleave',event=>event.currentTarget.classList.remove('dragging'));
aiEl('aiDropZone').addEventListener('drop',event=>{event.preventDefault();event.currentTarget.classList.remove('dragging');void aiUpload(event.dataTransfer.files[0]);});
aiEl('aiDocumentList').addEventListener('click',event=>{if(event.target.id==='aiRetryList'){void loadAiDocuments();return;}const card=event.target.closest('[data-ai-document]');if(card)void selectAiDocument(card.dataset.aiDocument);});
aiEl('aiPrevPage').addEventListener('click',()=>{aiState.page--;void loadAiDocuments();});
aiEl('aiNextPage').addEventListener('click',()=>{aiState.page++;void loadAiDocuments();});
aiEl('aiMoreContent').addEventListener('click',()=>void loadAiContent(aiState.viewerId,aiState.contentPage+1,true));
aiEl('aiProcessDocument').addEventListener('click',async()=>{try{aiEl('aiViewerStatus').textContent='Đang đọc nội dung…';await aiRequest(`/api/documents/${aiState.selectedId}/process`,{method:'POST',body:'{}'});await loadAiDocuments();await selectAiDocument(aiState.selectedId);}catch(error){aiEl('aiViewerStatus').textContent=error.message;}});
aiEl('aiOcrDocument').addEventListener('click',async()=>{try{await aiRequest(`/api/documents/${aiState.selectedId}/ocr`,{method:'POST',body:'{}'});}catch(error){aiEl('aiViewerStatus').textContent=error.message;}});
aiEl('aiLinkDocument').addEventListener('click',async()=>{if(!aiState.selectedId)return;const code=aiEl('aiTenderCode').value.trim();try{const data=await aiRequest(`/api/documents/${aiState.selectedId}/link`,{method:'POST',body:JSON.stringify({tender_code:code})});const index=aiState.documents.findIndex(item=>item.id===aiState.selectedId);if(index>=0)aiState.documents[index]=data.document;renderAiDocuments();refreshAiDocument(data.document);aiEl('aiViewerStatus').textContent=code?'Đã liên kết tài liệu với mã gói.':'Đã bỏ liên kết mã gói.';}catch(error){aiEl('aiViewerStatus').textContent=error.message;}});
aiEl('aiDeleteDocument').addEventListener('click',async()=>{if(!aiState.selectedId||!window.confirm('Xóa tài liệu này và toàn bộ phân tích liên quan?'))return;try{await aiRequest(`/api/documents/${aiState.selectedId}/delete`,{method:'POST',body:'{}'});aiState.selectedId='';aiEl('aiDocumentContent').innerHTML='';aiEl('aiAnalysisResult').innerHTML='';aiEl('aiDocumentTitle').textContent='Nội dung hồ sơ';aiEl('aiDownloadDocument').classList.add('hidden');aiEl('aiLinkDocument').hidden=true;aiEl('aiProcessDocument').hidden=true;aiEl('aiOcrDocument').hidden=true;aiEl('aiDeleteDocument').hidden=true;await loadAiDocuments();}catch(error){aiEl('aiViewerStatus').textContent=error.message;}});
document.querySelectorAll('[data-ai-tab]').forEach(button=>button.addEventListener('click',()=>chooseAiTab(button.dataset.aiTab)));
aiEl('aiRunAnalysis').addEventListener('click',()=>void runAiAnalysis());
aiEl('aiRefreshAnalysis').addEventListener('click',()=>void runAiAnalysis(true));
aiEl('aiAnalysisResult').addEventListener('click',event=>{const button=event.target.closest('[data-ai-citation]');if(button)void jumpAiCitation(button.dataset.aiCitation);});
aiEl('aiDocumentContent').addEventListener('click',event=>{const button=event.target.closest('[data-ai-copy-source]');if(button){const text=button.closest('.ai-source-block')?.querySelector('p')?.textContent||'';void copyText(text).then(()=>toast('Đã sao chép đoạn nguồn.'));}});
aiEl('aiHistoryList').addEventListener('click',event=>{const button=event.target.closest('[data-ai-history]');const item=aiState.history?.find(entry=>entry.id===button?.dataset.aiHistory);if(item)renderAiAnalysis(item);});
aiEl('aiExportXlsx').addEventListener('click',()=>void exportAi('xlsx'));
aiEl('aiExportDocx').addEventListener('click',()=>void exportAi('docx'));
aiEl('aiCopyResult').addEventListener('click',()=>void copyText(aiEl('aiAnalysisResult').innerText).then(()=>toast('Đã sao chép phân tích.')));
document.getElementById('drawerBody').addEventListener('click',event=>{const button=event.target.closest('[data-ai-tender-document]');if(button){closeDetail();showView('ai');void loadAiWorkspace().then(()=>selectAiDocument(button.dataset.aiTenderDocument));}});
if(document.body.dataset.view==='ai')void loadAiWorkspace();
setInterval(async()=>{if(document.body.dataset.view!=='ai'||!aiState.selectedId)return;const doc=aiState.documents.find(item=>item.id===aiState.selectedId);if(!doc||!['uploaded','extracting'].includes(doc.status))return;try{const data=await aiRequest(`/api/documents/${doc.id}`);if(data.document.status!==doc.status){const index=aiState.documents.findIndex(item=>item.id===doc.id);if(index>=0)aiState.documents[index]=data.document;renderAiDocuments();refreshAiDocument(data.document);if(data.document.status==='ready')await loadAiContent(doc.id,1);}}catch{}},10000);
