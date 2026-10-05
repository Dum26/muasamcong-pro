/* Local Search Engine 2.0. The existing live e-GP form remains independent. */
(() => {
  const node = id => document.getElementById(id);
  const panel = node('localSearchPanel');
  if (!panel) return;
  const state = {page: 1, pages: 0, controller: null};
  const fields = {kind: node('localSearchKind'), sort: node('localSearchSort'),
    page_size: node('localSearchSize')};
  const advanced = {from: node('localSearchFrom'), to: node('localSearchTo'),
    deadline_from: node('localSearchDeadlineFrom'), deadline_to: node('localSearchDeadlineTo'),
    status: node('localSearchStatusFilter'), location: node('localSearchLocation'),
    investor: node('localSearchInvestor'), procurer: node('localSearchProcurer'),
    contractor: node('localSearchContractor'), selection_method: node('localSearchMethod'),
    contract_type: node('localSearchContract'), price_min: node('localSearchPriceMin'),
    price_max: node('localSearchPriceMax'), results: node('localSearchResults')};
  const filterNames = {from:'Từ ngày',to:'Đến ngày',deadline_from:'Đóng thầu từ',
    deadline_to:'Đóng thầu đến',status:'Trạng thái',location:'Địa điểm',
    investor:'Chủ đầu tư',procurer:'Bên mời thầu',contractor:'Nhà thầu',
    selection_method:'Hình thức',contract_type:'Hợp đồng',price_min:'Giá từ',
    price_max:'Giá đến',results:'KQLCNT'};
  const kindNames = {tender: 'TBMT', plan: 'KHLCNT', investor: 'Chủ đầu tư',
    procurer: 'Bên mời thầu', contractor: 'Nhà thầu'};
  const dateText = value => value ? String(value).replace('T', ' ').slice(0, 16) : '—';
  const moneyText = value => value == null ? '—' : Number(value).toLocaleString('vi-VN') + ' ₫';
  function appendHighlighted(cell, value, query) {
    const source = String(value || '—');
    const needle = String(query || '').normalize('NFD').toLowerCase()
      .replace(/[\u0300-\u036f]/g, '').replaceAll('đ', 'd').trim();
    if (!needle || needle.includes(':')) {cell.textContent = source; return;}
    let folded = '', offsets = [];
    for (let i = 0; i < source.length;) {
      const point = String.fromCodePoint(source.codePointAt(i));
      const plain = point.normalize('NFD').toLowerCase()
        .replace(/[\u0300-\u036f]/g, '').replaceAll('đ', 'd');
      for (const char of plain) {folded += char; offsets.push([i, i + point.length]);}
      i += point.length;
    }
    const position = folded.indexOf(needle);
    if (position < 0) {cell.textContent = source; return;}
    const start = offsets[position][0], end = offsets[position + needle.length - 1][1];
    const mark = document.createElement('mark'); mark.textContent = source.slice(start, end);
    cell.append(document.createTextNode(source.slice(0, start)), mark,
      document.createTextNode(source.slice(end)));
  }
  let saved = [];
  async function loadSaved() {
    try {
      const response = await fetch('/api/presets', {credentials: 'same-origin'});
      if (!response.ok) return;
      saved = ((await response.json()).presets || []).filter(item => item.params?.mode === 'Kho dữ liệu');
      const select = node('localSearchSaved');
      select.replaceChildren(new Option('Chọn bộ lọc…', ''));
      saved.forEach(item => select.add(new Option(item.name, item.id)));
    } catch { /* Saved filters are optional to search availability. */ }
  }
  const detailPath = item => item.kind === 'tender' ? '/app/tenders/' + encodeURIComponent(item.code) :
    item.kind === 'plan' ? '/app/plans/' + encodeURIComponent(item.code) :
    '/app/entities/' + encodeURIComponent(item.kind) + '/' + encodeURIComponent(item.code);
  function params() {
    const result = new URLSearchParams({q: node('keyword').value.trim(), page: String(state.page)});
    for (const [key, field] of Object.entries(fields)) if (field.value) result.set(key, field.value);
    for (const [key, field] of Object.entries(advanced)) {
      const value = field.type === 'checkbox' ? (field.checked ? '1' : '') : field.value.trim();
      if (value) result.set(key, value);
    }
    return result;
  }
  function renderChips() {
    const container = node('localSearchChips');
    container.replaceChildren();
    for (const [key, field] of Object.entries(advanced)) {
      const value = field.type === 'checkbox' ? (field.checked ? 'Có kết quả' : '') : field.value.trim();
      if (!value) continue;
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `${filterNames[key]}: ${value} ×`;
      button.addEventListener('click', () => {
        if (field.type === 'checkbox') field.checked = false; else field.value = '';
        state.page = 1; void searchLocal();
      });
      container.append(button);
    }
  }
  async function recordHistory(total, query) {
    const params = {mode: 'Kho dữ liệu', keyword: query.get('q') || '',
      kind: query.get('kind') || '', sort: query.get('sort') || 'relevance',
      page_size: query.get('page_size') || '25',
      ...Object.fromEntries(Object.keys(advanced).map(key => [key, query.get(key) || '']))};
    try {
      const created = await fetch('/api/history', {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({params})});
      if (!created.ok) return;
      const response = await fetch('/api/history', {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'complete', params, result_count: total})});
      if (response.ok && typeof loadHistory === 'function') void loadHistory();
    } catch { /* Search stays usable if history storage is unavailable. */ }
  }
  async function searchLocal(updateUrl = true, forceRefresh = false) {
    state.controller?.abort();
    const controller = new AbortController();
    state.controller = controller;
    panel.hidden = false;
    renderChips();
    node('localSearchStatus').textContent = 'Đang tìm trong dữ liệu đã đồng bộ…';
    const query = params();
    if (updateUrl) history.pushState({view: 'search'}, '', '/app/search?' + query.toString());
    try {
      const response = await fetch('/api/intelligence/search?' + query.toString() + (forceRefresh ? '&refresh=1' : ''),
        {credentials: 'same-origin', signal: controller.signal});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Không lấy được dữ liệu tìm kiếm.');
      if (controller.signal.aborted) return;
      state.pages = data.total_pages;
      const body = node('localSearchRows');
      body.replaceChildren();
      for (const item of data.items) {
        const row = document.createElement('tr');
        const values = [kindNames[item.kind] || item.kind, item.code, item.name,
          item.investor, dateText(item.published), dateText(item.deadline),
          moneyText(item.price), dateText(item.updated)];
        values.forEach((value, index) => {
          const cell = document.createElement('td');
          if (index === 1) {
            const link = document.createElement('a');
            link.href = detailPath(item);
            link.textContent = value || '—';
            cell.append(link);
          } else if (index === 2 || index === 3) appendHighlighted(cell, value, node('keyword').value);
          else {
            cell.textContent = value || '—';
            if (index === 7 && item.updated && Date.now() - Date.parse(item.updated) > 6 * 3600_000) {
              const stale = document.createElement('small'); stale.className = 'local-stale';
              stale.textContent = 'Dữ liệu cũ'; cell.append(stale);
            }
          }
          row.append(cell);
        });
        const actions = document.createElement('td');
        const copy = document.createElement('button');
        copy.type = 'button'; copy.className = 'local-action'; copy.textContent = 'Sao chép mã';
        copy.addEventListener('click', async () => {
          try {await navigator.clipboard.writeText(item.code); copy.textContent = 'Đã sao chép';}
          catch {copy.textContent = 'Không sao chép được';}
        });
        actions.append(copy);
        if (item.kind === 'tender' || item.kind === 'plan') {
          const follow = document.createElement('button');
          follow.type = 'button'; follow.className = 'local-action'; follow.textContent = '☆ Theo dõi';
          follow.addEventListener('click', async () => {
            follow.disabled = true;
            try {
              const response = await fetch('/api/watchlist', {method: 'POST', credentials: 'same-origin',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action:'add',
                  code:item.code,name:item.name,investor:item.investor,deadline:item.deadline})});
              if (!response.ok) throw new Error('Không theo dõi được gói này.');
              follow.textContent = '★ Đang theo dõi';
              if (typeof loadWatchlist === 'function') void loadWatchlist();
            } catch (error) {follow.textContent = error.message; follow.disabled = false;}
          });
          actions.append(follow);
        }
        row.append(actions);
        body.append(row);
      }
      node('localSearchStatus').textContent = data.total ?
        `${data.total.toLocaleString('vi-VN')} kết quả trong kho dữ liệu` :
        'Không tìm thấy dữ liệu phù hợp. Hãy kiểm tra mã, giảm bộ lọc hoặc quét dữ liệu mới.';
      node('localSearchPage').textContent = `Trang ${data.page} / ${data.total_pages || 1}`;
      node('localSearchPrev').disabled = state.page <= 1;
      node('localSearchNext').disabled = state.page >= state.pages;
      if (updateUrl && state.page === 1) void recordHistory(data.total, query);
    } catch (error) {
      if (error.name === 'AbortError') return;
      node('localSearchStatus').textContent = 'Không lấy được dữ liệu: ' + error.message;
      node('localSearchRows').replaceChildren();
    }
  }
  node('localSearchButton').addEventListener('click', () => {state.page = 1; void searchLocal();});
  node('localSearchRefresh').addEventListener('click', () => {void searchLocal(false, true);});
  node('localSearchSave').addEventListener('click', async () => {
    const name = node('localSearchName').value.trim();
    if (!name) {node('localSearchStatus').textContent = 'Nhập tên bộ lọc trước khi lưu.'; return;}
    const params = {mode: 'Kho dữ liệu', keyword: node('keyword').value.trim(),
      kind: fields.kind.value, sort: fields.sort.value, page_size: fields.page_size.value,
      ...Object.fromEntries(Object.entries(advanced).map(([key, field]) =>
        [key, field.type === 'checkbox' ? (field.checked ? '1' : '') : field.value.trim()]))};
    try {
      const response = await fetch('/api/presets', {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'save', name, params})});
      if (!response.ok) throw new Error((await response.json()).error || 'Không lưu được bộ lọc.');
      await loadSaved();
      node('localSearchStatus').textContent = `Đã lưu bộ lọc “${name}”.`;
    } catch (error) {node('localSearchStatus').textContent = error.message;}
  });
  node('localSearchLoad').addEventListener('click', () => {
    const item = saved.find(entry => entry.id === node('localSearchSaved').value);
    if (!item) return;
    node('localSearchName').value = item.name;
    window.restoreLocalSearch(item.params);
  });
  node('localSearchSaved').addEventListener('change', () => {
    const item = saved.find(entry => entry.id === node('localSearchSaved').value);
    node('localSearchWatch').disabled = !item;
    node('localSearchWatch').textContent = item?.is_watch_enabled ? 'Tắt theo dõi' : 'Bật theo dõi';
  });
  node('localSearchWatch').addEventListener('click', async () => {
    const item = saved.find(entry => entry.id === node('localSearchSaved').value);
    if (!item) return;
    try {
      const response = await fetch('/api/presets', {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'watch', id: item.id, enabled: !item.is_watch_enabled})});
      if (!response.ok) throw new Error((await response.json()).error || 'Không đổi được trạng thái theo dõi.');
      const selected = item.id;
      await loadSaved();
      node('localSearchSaved').value = selected;
      node('localSearchSaved').dispatchEvent(new Event('change'));
      node('localSearchStatus').textContent = item.is_watch_enabled ? 'Đã tắt theo dõi.' : 'Đã bật theo dõi bộ lọc.';
    } catch (error) {node('localSearchStatus').textContent = error.message;}
  });
  node('localSearchClose').addEventListener('click', () => {state.controller?.abort(); panel.hidden = true;});
  node('localSearchPrev').addEventListener('click', () => {if (state.page > 1) {state.page--; void searchLocal();}});
  node('localSearchNext').addEventListener('click', () => {if (state.page < state.pages) {state.page++; void searchLocal();}});
  Object.values(fields).forEach(field => field.addEventListener('change', () => {state.page = 1; void searchLocal();}));
  Object.values(advanced).forEach(field => field.addEventListener('change', () => {state.page = 1; void searchLocal();}));
  node('localSearchClear').addEventListener('click', () => {
    Object.values(advanced).forEach(field => {if (field.type === 'checkbox') field.checked = false; else field.value = '';});
    state.page = 1; void searchLocal();
  });
  function restoreUrl() {
    if (location.pathname !== '/app/search') return;
    const query = new URLSearchParams(location.search);
    node('keyword').value = query.get('q') || '';
    for (const [key, field] of Object.entries(fields)) field.value = query.get(key) || field.options[0].value;
    for (const [key, field] of Object.entries(advanced)) {
      if (field.type === 'checkbox') field.checked = query.get(key) === '1';
      else field.value = query.get(key) || '';
    }
    state.page = Math.max(1, Number(query.get('page')) || 1);
    if (typeof showView === 'function') showView('search', false);
    void searchLocal(false);
  }
  window.restoreLocalSearch = item => {
    node('keyword').value = item.keyword || '';
    fields.kind.value = item.kind || '';
    fields.sort.value = item.sort || 'relevance';
    fields.page_size.value = item.page_size || '25';
    for (const [key, field] of Object.entries(advanced)) {
      if (field.type === 'checkbox') field.checked = item[key] === '1';
      else field.value = item[key] || '';
    }
    state.page = 1;
    if (typeof showView === 'function') showView('search', false);
    void searchLocal();
  };
  window.addEventListener('popstate', restoreUrl);
  restoreUrl();
  void loadSaved();
})();
