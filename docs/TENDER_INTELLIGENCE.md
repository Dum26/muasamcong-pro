# Dữ liệu đấu thầu 4.1

Trang `/app/intelligence` đọc kho TBMT/KHLCNT đã thu thập từ các truy vấn e-GP. Trang hồ sơ có URL cố định `/app/tenders/<IB...>`, `/app/plans/<PL...>` và `/app/investors/<id>`, `/app/contractors/<id>`, `/app/procurers/<id>`. Tất cả trang và API intelligence đều yêu cầu đăng nhập. Dữ liệu theo dõi và ghi chú vẫn thuộc tài khoản riêng; kho TBMT chỉ chứa dữ liệu công khai từ nguồn.

Migration schema v4 tạo `tenders`, `plans`, `investors`, `procuring_entities`, `contractors`, `tender_snapshots`, `tender_changes`, `tender_events`, `tender_source_documents`, `document_versions`, `background_jobs`, `alert_rules`, `user_preferences`, `audit_logs` và các index. Migration dùng `create_all(checkfirst=True)`, không xóa dữ liệu cũ. Lần chạy ứng dụng đầu tiên sau cập nhật sẽ nâng schema tự động. Với Cloud Run, dùng PostgreSQL qua `DATABASE_URL`; SQLite chỉ phù hợp chạy local.

Kết quả tra cứu hoàn tất được nhập vào kho theo mã TBMT duy nhất. Snapshot chỉ được thêm khi trường nguồn thay đổi. Mốc timeline chỉ có khi nguồn cung cấp ngày hoặc có thay đổi được phát hiện; tài liệu chỉ được ghi khi e-GP trả liên kết HTTPS rõ ràng. Mở hồ sơ ưu tiên dữ liệu đã cache. Nút **Cập nhật nguồn** gọi lại e-GP, giới hạn 6 lần/phút cho mỗi tài khoản. Khi nguồn lỗi, yêu cầu được đưa vào `background_jobs` để thử lại tối đa 3 lần với backoff.

Cloud Scheduler có thể gọi `POST /internal/jobs/sync-tenders` với header `X-Job-Secret: <JOB_SECRET>` theo chu kỳ. Endpoint này xử lý tối đa 5 job mỗi lượt; không có worker chạy vô hạn trong Cloud Run. Cùng endpoint nội bộ có thể được gọi khi vận hành local. Không đưa `JOB_SECRET` vào mã nguồn hoặc frontend. Admin xem trạng thái tại `/admin`.

API chính: `GET /api/intelligence/tenders` hỗ trợ `page`, `page_size`, `q`, `status`, `investor_id`, `contractor_id`, `from`, `to`, `sort`, `order`, `results`; `GET /api/intelligence/tenders/<code>`; `POST /api/intelligence/tenders/<code>/refresh`; `GET /api/intelligence/plans/<code>`; `GET /api/intelligence/entities/<kind>/<id>`; `GET /api/intelligence/analytics`; `GET /api/intelligence/deadlines`; `GET /api/intelligence/compare?code=...&code=...`; `GET /api/intelligence/admin/sync` (admin). Các list trả `items`, `page`, `page_size`, `total`.

Giới hạn hiện tại: e-GP có thể không trả tài liệu trực tiếp, mã số thuế, giá trúng hoặc ngày KQLCNT; các trường này được để trống. Chưa có tải tài liệu nguồn on-demand và diff nội dung nhị phân, chưa có bộ quy tắc cảnh báo tùy biến, xuất XLSX cho các view intelligence, hay PostgreSQL full-text index. Các trang SEO công khai không xuất dữ liệu tài khoản hay dữ liệu intelligence riêng tư.

Kiểm thử: `./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py'` trên Windows và `npm test`. Khởi động local bằng `./.venv/Scripts/python.exe web_main.py`; đăng nhập rồi mở `/app/intelligence`.
