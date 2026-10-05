# MuaSamCong Pro 4.2 — BI và báo cáo

Mở `/app/analytics` sau khi đăng nhập. Dashboard BI tổng hợp từ các bảng TBMT/KHLCNT đã thu thập trên server; dashboard Phân tích truy vấn cũ tại `/app/analysis` vẫn hoạt động. BI dùng cùng cách vẽ SVG hiện có, không thêm chart library hay framework frontend.

Các route giao diện: `/app/analytics`, `/app/analytics/tenders`, `/app/analytics/khlcnt`, `/app/analytics/kqlcnt`, `/app/analytics/contractors`, `/app/analytics/investors`, `/app/analytics/geography`, `/app/analytics/deadlines`, `/app/analytics/changes`, `/app/reports/new`, `/app/dashboard/custom`. URL analytics giữ bộ lọc ngày/trạng thái/địa điểm/đơn vị, không chứa dữ liệu riêng tư. Mọi route `/app/*` vẫn yêu cầu đăng nhập và có `noindex`.

Migration v5 thêm `saved_reports`, `report_runs`, `user_dashboards` và index theo `user_id`/thời gian. Migration tạo bảng tại chỗ; không xóa dữ liệu người dùng. Production tiếp tục dùng PostgreSQL qua `DATABASE_URL`. Báo cáo và dashboard được truy xuất bằng cả `id` lẫn `user_id`; tài khoản khác nhận 404.

API:

- `GET /api/analytics/overview`: KPI, độ phủ giá, xu hướng ngày/tuần/tháng/quý/năm, nhóm trạng thái/địa điểm/chủ đầu tư/nhà thầu, kỳ trước và cùng kỳ năm trước khi có ngày bắt đầu/kết thúc.
- `GET /api/reports/schema`: danh sách dataset/trường hợp lệ cho builder.
- `POST /api/reports/preview`: truy vấn có whitelist, phân trang tối đa 100 dòng/lượt.
- `GET/POST /api/reports`, `GET/POST /api/reports/{id}`, `POST /api/reports/{id}/run`, `GET /api/reports/{id}/runs`: lưu, sửa, nhân bản, ghim, chạy, xóa và lịch sử chạy.
- `POST /api/reports/export`: Excel hoặc CSV. Tối đa 5.000 dòng; nếu nhiều hơn, người dùng phải thêm bộ lọc. Excel có filter, hàng tiêu đề cố định, định dạng số/ngày và sheet thông tin. CSV/XLSX xử lý chuỗi bắt đầu bằng ký tự công thức. File được lưu trong Download Center của đúng tài khoản để tải lại trong 24 giờ.
- `GET/POST /api/dashboards`, `GET/POST /api/dashboards/{id}`, `POST /api/dashboards/{id}/run`: lưu dashboard riêng, đặt mặc định, xóa và chạy widget. Mỗi dashboard có tối đa 12 widget. Không có worker refresh liên tục.

Report Builder chỉ chấp nhận dataset, cột, toán tử lọc, nhóm, phép tổng hợp và trường sắp xếp nằm trong whitelist backend. Không nhận SQL hay biểu thức tùy ý. `SUM`/`AVG` chỉ hợp lệ với giá trị số. Dữ liệu nguồn, ghi chú và tài liệu AI riêng tư không được trộn vào aggregate công khai. KPI giá luôn hiển thị số dòng có giá; tỷ lệ tiết kiệm chỉ tính khi có cả giá gói > 0 và giá trúng. Chênh lệch giá chỉ là số học, không phải đánh giá chất lượng nhà thầu.

Giới hạn hiện tại: chưa có PDF export, share báo cáo theo team, dashboard kéo thả, thông báo lịch báo cáo hoặc materialized view. Đơn vị/địa điểm phụ thuộc tên từ nguồn; hệ thống không suy đoán trường còn thiếu. Bộ lọc không phù hợp với KHLCNT được hiển thị là không so sánh được.

Kiểm tra local: `./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py'`, `npm test`, rồi chạy `./.venv/Scripts/python.exe web_main.py` và mở `/app/analytics`.
