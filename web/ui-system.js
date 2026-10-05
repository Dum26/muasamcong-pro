/* Presentation-only enhancements. Search, export and persistence remain in the existing modules. */
(() => {
  const byId = id => document.getElementById(id);
  const drawIcons = root => {
    if (!window.lucide?.createIcons) return;
    window.lucide.createIcons({root});
    root.querySelectorAll('svg[data-lucide]').forEach(icon => icon.removeAttribute('data-lucide'));
  };
  drawIcons(document);
  let iconFrame = 0;
  const iconRoots = new Set();
  new MutationObserver(records => {
    for (const record of records) {
      if ([...record.addedNodes].some(node => node.nodeType === 1 &&
        (node.matches?.('[data-lucide]:not(svg)') || node.querySelector?.('[data-lucide]:not(svg)')))) iconRoots.add(record.target);
    }
    if (!iconRoots.size || iconFrame) return;
    iconFrame = requestAnimationFrame(() => {
      iconFrame = 0;
      for (const root of iconRoots) if (root.isConnected) drawIcons(root);
      iconRoots.clear();
    });
  }).observe(document.body, {childList:true, subtree:true});

  const themeButton = byId('themeToggle');
  const syncThemeButton = () => {
    const dark = document.body.classList.contains('dark');
    themeButton.setAttribute('aria-label', dark ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối');
    themeButton.setAttribute('title', themeButton.getAttribute('aria-label'));
    themeButton.setAttribute('aria-pressed', String(dark));
    themeButton.innerHTML = `<i data-lucide="${dark ? 'sun' : 'moon'}" aria-hidden="true"></i>`;
  };
  themeButton.addEventListener('click', syncThemeButton);
  byId('settingsTheme').addEventListener('click', () => requestAnimationFrame(syncThemeButton));
  syncThemeButton();

  const sidebarButton = byId('collapseSidebar');
  const syncSidebarButton = () => {
    const collapsed = document.body.classList.contains('sidebar-collapsed');
    sidebarButton.setAttribute('aria-label', collapsed ? 'Mở rộng thanh bên' : 'Thu gọn thanh bên');
    sidebarButton.setAttribute('title', sidebarButton.getAttribute('aria-label'));
    sidebarButton.setAttribute('aria-expanded', String(!collapsed));
    sidebarButton.innerHTML = `<i data-lucide="${collapsed ? 'panel-left-open' : 'panel-left-close'}" aria-hidden="true"></i>`;
  };
  sidebarButton.addEventListener('click', syncSidebarButton);
  syncSidebarButton();
  document.querySelector('.global-search').addEventListener('click', event => {
    if (event.target !== byId('globalSearch')) openPalette();
  });
  const syncNavigation = () => document.querySelectorAll('[data-view]').forEach(button => {
    if (button.classList.contains('active')) button.setAttribute('aria-current','page');
    else button.removeAttribute('aria-current');
  });
  new MutationObserver(syncNavigation).observe(document.querySelector('.nav-list'), {subtree:true,attributes:true,attributeFilter:['class']});
  syncNavigation();

  const filterFields = [
    ['keyword','Từ khóa',''], ['dateFrom','Từ ngày',''], ['dateTo','Đến ngày',''],
    ['statusFilter','Trạng thái','Tất cả trạng thái'], ['searchFormFilter','Hình thức',''],
    ['searchLocationFilter','Địa điểm','']
  ];
  const activeFilters = byId('activeFilters');
  function renderActiveFilters() {
    activeFilters.replaceChildren();
    for (const [id,label,defaultValue] of filterFields) {
      if ((id === 'dateFrom' || id === 'dateTo') && !byId('useDates').checked) continue;
      const field = byId(id), value = field.value.trim();
      if (!value || value === defaultValue) continue;
      const chip = document.createElement('button');
      chip.type = 'button'; chip.className = 'filter-chip'; chip.dataset.clearFilter = id;
      chip.setAttribute('aria-label', `Bỏ lọc ${label}: ${value}`);
      chip.append(document.createTextNode(`${label}: ${value}`));
      const close = document.createElement('i'); close.setAttribute('data-lucide','x'); close.setAttribute('aria-hidden','true');
      chip.append(close); activeFilters.append(chip);
    }
    activeFilters.hidden = !activeFilters.childElementCount;
  }
  const form = byId('searchForm');
  form.addEventListener('input', renderActiveFilters);
  form.addEventListener('change', renderActiveFilters);
  activeFilters.addEventListener('click', event => {
    const chip = event.target.closest('[data-clear-filter]');
    if (!chip) return;
    const field = byId(chip.dataset.clearFilter); field.value = '';
    field.dispatchEvent(new Event('change', {bubbles:true}));
    renderActiveFilters(); field.focus();
  });
  for (const id of ['resetSearch','loadPreset']) byId(id).addEventListener('click', () => requestAnimationFrame(renderActiveFilters));
  document.querySelectorAll('[data-date-range]').forEach(button => button.addEventListener('click', () => requestAnimationFrame(renderActiveFilters)));
  const baseRestoreQuery = restoreQuery;
  restoreQuery = function(params) {baseRestoreQuery(params); renderActiveFilters();};
  renderActiveFilters();

  let detailReturnFocus = null, paletteReturnFocus = null;
  const baseOpenDetailRow = openDetailRow;
  openDetailRow = function(row) {
    if (!byId('detailDrawer').classList.contains('open')) detailReturnFocus = document.activeElement;
    baseOpenDetailRow(row);
    byId('closeDrawer').focus({preventScroll:true});
  };
  const baseCloseDetail = closeDetail;
  closeDetail = function() {
    baseCloseDetail();
    if (detailReturnFocus?.isConnected) detailReturnFocus.focus({preventScroll:true});
    detailReturnFocus = null;
  };
  const baseOpenPalette = openPalette;
  openPalette = function(initial = '') {
    if (byId('commandPalette').classList.contains('hidden')) paletteReturnFocus = document.activeElement;
    baseOpenPalette(initial);
  };
  const baseClosePalette = closePalette;
  closePalette = function() {
    baseClosePalette();
    if (paletteReturnFocus?.isConnected) paletteReturnFocus.focus({preventScroll:true});
    paletteReturnFocus = null;
  };
  document.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const panel = !byId('commandPalette').classList.contains('hidden') ? byId('commandPalette') :
      byId('detailDrawer').classList.contains('open') ? byId('detailDrawer') : null;
    if (!panel) return;
    const focusable = [...panel.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')]
      .filter(element => element.getClientRects().length);
    if (!focusable.length) return;
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last.focus();}
    else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
  });

  const menu = document.createElement('div');
  menu.className = 'row-action-menu hidden animate-in fade-in duration-200'; menu.setAttribute('role','menu');
  document.body.append(menu);
  let menuRow = null, menuTrigger = null;
  const closeMenu = () => {
    menu.classList.add('hidden'); menu.replaceChildren();
    menuTrigger?.setAttribute('aria-expanded','false'); menuRow = null; menuTrigger = null;
  };
  byId('resultBody').addEventListener('click', event => {
    const button = event.target.closest('[data-row-menu]');
    if (!button) return;
    event.stopPropagation();
    if (menuTrigger === button) {closeMenu(); return;}
    closeMenu();
    menuTrigger = button;
    menuRow = state.rows.find(row => row.index === Number(button.dataset.rowMenu));
    if (!menuRow) return;
    const code = menuRow.notify_no || planDisplayCode(menuRow);
    const actions = [
      ['eye','Xem chi tiết','detail'], ['copy','Sao chép mã','copy'],
      ['star',state.watchlist.some(item => item.code === code) ? 'Bỏ theo dõi' : 'Theo dõi','watch'],
      ['file-spreadsheet','Xuất Excel','export']
    ];
    if (officialDetailUrl(menuRow)) actions.push(['external-link','Mở nguồn e-GP','source']);
    menu.innerHTML = actions.map(([icon,label,action]) =>
      `<button type="button" role="menuitem" data-row-action="${action}"><i data-lucide="${icon}" aria-hidden="true"></i>${label}</button>`).join('');
    menu.classList.remove('hidden'); button.setAttribute('aria-expanded','true');
    const rect = button.getBoundingClientRect();
    const width = 196, height = actions.length * 39 + 10;
    menu.style.left = `${Math.max(8,Math.min(rect.right-width,innerWidth-width-8))}px`;
    menu.style.top = `${Math.max(8,Math.min(rect.bottom+4,innerHeight-height-8))}px`;
    menu.querySelector('button')?.focus({preventScroll:true});
  });
  menu.addEventListener('click', event => {
    const action = event.target.closest('[data-row-action]')?.dataset.rowAction;
    if (!action || !menuRow) return;
    const row = menuRow, code = row.notify_no || planDisplayCode(row);
    menuTrigger?.focus({preventScroll:true});
    closeMenu();
    if (action === 'detail') openDetailRow(row);
    if (action === 'copy') void copyText(code).then(() => toast(`Đã sao chép ${code}.`));
    if (action === 'watch') void toggleWatch(row);
    if (action === 'export') void exportDetailRow(row);
    if (action === 'source') window.open(officialDetailUrl(row),'_blank','noopener,noreferrer');
  });
  menu.addEventListener('keydown', event => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    event.preventDefault();
    const items = [...menu.querySelectorAll('button')], index = items.indexOf(document.activeElement);
    items[(index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
  });
  document.addEventListener('click', event => {if (!menu.contains(event.target) && !event.target.closest('[data-row-menu]')) closeMenu();});
  document.addEventListener('keydown', event => {if (event.key === 'Escape' && !menu.classList.contains('hidden')) {const trigger=menuTrigger;closeMenu(); trigger?.focus({preventScroll:true});}});
  byId('results').querySelector('.table-wrap').addEventListener('scroll',closeMenu,{passive:true});
})();
