# MuaSamCong Pro 5.1 — migration matrix

Ngày audit: 30/09/2026. `frontend/` là giao diện React/TypeScript/Vite mới cho `/app`; Docker image bật `REACT_FRONTEND_ENABLED=1`. `web/` vẫn phục vụ các trang SEO public và `/legacy` để kiểm tra tương thích. Chạy local bằng `REACT_FRONTEND_ENABLED=1` sau `cd frontend && npm run build`; khi chưa có build, server dùng giao diện cũ.

Chạy thử local: ở terminal 1 đặt `PORT=54939`, `REACT_FRONTEND_ENABLED=1`, `MUASAMCONG_NO_BROWSER=1` rồi chạy `python web_app.py`; ở terminal 2 chạy `cd frontend && npm ci && npm run dev`. Mở URL do Vite in ra. Khi kiểm tra bản build, chạy `npm run build` trong `frontend/` và mở `/login` trên Python server. Dockerfile đã build React bằng Node stage và Python serve static; chưa kiểm tra Docker thực tế vì máy hiện không có lệnh `docker`.

| Legacy module | React feature | Trạng thái | Kiểm thử / ghi chú |
| --- | --- | --- | --- |
| `auth.html`, `auth-ui.js` | AuthPage, AuthProvider | Có | Login/register/session; backend auth giữ nguyên |
| `workspace.js`, `ui-system.js` | App shell, router, Ctrl+K | Một phần | Sidebar/theme/route cơ bản; command palette nâng cao còn legacy |
| `app.js`, `search-engine.js` | SearchPage, ArchiveSearchPage, CodesPage | Một phần | Tra cứu trực tiếp và kho dữ liệu, gợi ý, filter URL, bảng, theo dõi, export, nhập `.xlsx/.csv/.txt`, sao chép cột, phân lô IB; quick preview và một số tùy chọn nâng cao còn cần đối chiếu |
| `workspace_plus.js` | WatchlistPage, HistoryPage, DownloadsPage | Một phần | Ghi chú, ưu tiên, ghim, thông báo, file; lịch sử khôi phục đủ filter; action nâng cao còn legacy |
| `intelligence.js` | DashboardPage, TenderPage, EntityPage | Một phần | KPI, hạn thầu, timeline, tài liệu, thay đổi, gói liên quan và hồ sơ đơn vị; cần đối chiếu chi tiết nâng cao và refresh dữ liệu |
| `analysis.js`, `bi.js` | AnalyticsPage, ReportBuilderPage | Một phần | KPI, xu hướng, drilldown, xuất Excel, tạo/sửa/chạy báo cáo, dashboard riêng và widget; cần kiểm thử trực tiếp với dữ liệu thật và các mẫu dashboard cũ |
| `automation.js` | AutomationPage | Một phần | React: danh sách, builder AND/OR, preview/test/chạy ngay, bật/tạm dừng, lịch sử/sự kiện, thống kê, nhập/xuất rule JSON; cần kiểm thử trình duyệt với rule thật |
| `document-center.js`, `ai-workspace.js` | DocumentsPage, AiPage | Một phần | React: danh mục, lọc, chi tiết, upload, download, trích xuất, phiên bản, tóm tắt, hỏi đáp, so sánh, dẫn nguồn, xuất AI. OCR và một số luồng tải file nguồn vẫn còn legacy |
| `admin-ui.js`, `data-quality.js`, `performance.js`, `production-status.js` | AdminPage, QualityPanel | Một phần | `/app/admin` và `/admin` khi bật React: số liệu, đồng bộ, quét lỗi, chi tiết/giải quyết/hoàn tác, cặp nghi trùng và hiệu năng; còn đối chiếu thống kê AI/tìm kiếm và job chi tiết; API enforce admin |
| `compare.js` | ComparePage | Có | So sánh 2–5 TBMT đã thu thập qua API; chọn từ bảng tra cứu hoặc nhập mã |
| `web/index.html` settings | SettingsPage | Một phần | Theme, sidebar, chọn thư mục cho Excel/Download Center, nhập dữ liệu cũ; chưa có API backend cho notification preferences |
| `style.css`, `pro.css`, `workspace.css`, `tailwind.css` | `frontend/src/styles.css` | Một phần | Chưa xóa CSS cũ; public SEO HTML nằm ngoài React |

Audit tập trung vào DOM IDs/event listeners, fetch endpoints, localStorage, bảng, dialog/drawer, keyboard shortcuts, chart, upload/download. Các URL API đều same-origin. Dữ liệu tài khoản (theo dõi, lịch sử, bộ lọc, tài liệu) nằm ở backend; localStorage React chỉ giữ theme/sidebar. Public SEO `/` và `/loc-du-lieu-mua-sam-cong` tiếp tục dùng HTML server-render, không đưa vào SPA.

## Còn cần để đạt acceptance 5.1

Đã chạy `npm run build` (gồm strict TypeScript), `npm run lint`, `npm test` (9 file/14 test), bộ test Python (151 test), test JS cũ (9 suite) và smoke Chrome headless: 14 route, login/logout, quyền admin, các tab admin, upload tài liệu, xem trước/lưu báo cáo, lưu/chạy dashboard, xem trước/lưu automation rule. Kết quả tra cứu trực tiếp chưa đồng bộ vào kho vẫn mở được chi tiết xem nhanh. Docker image bật React cho `/app`; không còn liên kết từ React về `/legacy`. Máy phát triển chưa có Docker nên chưa xác minh `docker build` hoặc Cloud Run thực tế.

Vẫn cần đối chiếu trên dữ liệu production các nhánh nâng cao đánh dấu “Một phần”: quick preview, OCR, tùy chọn nâng cao của AI/Admin, mẫu dashboard cũ và notification preferences (backend chưa có API). Giữ `/legacy` làm đường lui trong giai đoạn này; không xóa Vanilla. Không cài shadcn/ui trong 5.1.
