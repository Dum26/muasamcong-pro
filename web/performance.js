(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g,
    char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  async function load() {
    try {
      const response = await fetch('/api/admin/performance');
      if (!response.ok) throw new Error('Không lấy được số liệu hiệu năng.');
      const data = await response.json();
      $('perfStatus').textContent = 'Số liệu trong bộ nhớ của instance đang phục vụ; làm mới khi cần.';
      $('perfStats').innerHTML = [
        ['Yêu cầu', data.request_count], ['Lỗi 5xx', data.error_count_5xx],
        ['p50', `${data.p50_ms} ms`], ['p95', `${data.p95_ms} ms`],
        ['Job chờ', data.queue_length]
      ].map(([label,value])=>`<article><span>${esc(label)}</span><strong>${esc(value)}</strong></article>`).join('');
      $('perfRoutes').innerHTML = data.routes.length ?
        `<table class="dq-issues"><thead><tr><th>Đường dẫn</th><th>Lượt</th><th>p50</th><th>p95</th><th>SQL TB</th><th>Lỗi 5xx</th></tr></thead><tbody>${data.routes.map(item=>`<tr><td><code>${esc(item.route)}</code></td><td>${esc(item.count)}</td><td>${esc(item.p50_ms)} ms</td><td>${esc(item.p95_ms)} ms</td><td>${esc(item.db_query_avg)}</td><td>${esc(item.errors_5xx)}</td></tr>`).join('')}</tbody></table>` : '<p>Chưa có yêu cầu nào trên instance này.</p>';
      $('perfStatus').textContent += ` Pool DB: ${data.db_pool}.`;
    } catch (error) { $('perfStatus').textContent = error.message; }
  }
  $('perfRefresh').addEventListener('click', () => void load());
  if (location.pathname === '/admin/performance')
    requestAnimationFrame(() => $('performanceCenter').scrollIntoView({block:'start'}));
  void load();
})();
