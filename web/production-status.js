(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const labels = {ready:'Sẵn sàng', unavailable:'Không lấy được dữ liệu',
    schema_outdated:'Cần migration', local:'Lưu local', no_samples:'Chưa có mẫu',
    Healthy:'Ổn định', Degraded:'Suy giảm', Unavailable:'Gián đoạn'};
  async function load() {
    $('productionRefresh').disabled = true;
    try {
      const response = await fetch('/api/admin/production-status');
      if (!response.ok) throw new Error('Không lấy được trạng thái vận hành.');
      const data = await response.json();
      const cards = [
        ['Môi trường', data.environment], ['Phiên bản', data.version],
        ['Bản build', data.build_sha || 'Chưa gắn SHA'],
        ['Database', data.database], ['Lưu trữ', data.storage],
        ['Nguồn e-GP', data.source], ['Job chờ', data.queue_length],
        ['Lỗi 5xx gần đây', data.recent_5xx]
      ];
      $('productionStats').replaceChildren(...cards.map(([label, value]) => {
        const card = document.createElement('article');
        const title = document.createElement('span');
        const figure = document.createElement('strong');
        title.textContent = label;
        figure.textContent = labels[value] || (value ?? 'Không lấy được dữ liệu');
        card.append(title, figure);
        return card;
      }));
      $('productionStatus').textContent = 'Cập nhật lúc ' + new Date().toLocaleString('vi-VN');
    } catch (error) {
      $('productionStatus').textContent = error.message;
    } finally {
      $('productionRefresh').disabled = false;
    }
  }
  $('productionRefresh').addEventListener('click', load);
  void load();
})();
