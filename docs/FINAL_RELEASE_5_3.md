# MuaSamCong Pro 5.3 — release gate

Ngày kiểm tra: 01/10/2026. **Trạng thái: local release candidate đạt; public production release CHƯA đạt.** Không có URL public hoặc deployment nào được tạo trong lượt kiểm tra này.

## Kiến trúc và phạm vi

React 19 + TypeScript 6 + Vite 8 + Tailwind 4 + shadcn/ui phục vụ `/app`; Python giữ HTTP/API và các luồng nghiệp vụ. SQLite dùng local, PostgreSQL + GCS bắt buộc trong production. Trang SEO public ở `/` và `/loc-du-lieu-mua-sam-cong`; `/legacy` giữ giao diện Vanilla để đối chiếu.

5.3 đã rà và chỉnh App Shell, Tra cứu, Chi tiết, biểu đồ Phân tích và đường dẫn quản trị. Các trang Theo dõi, Tài liệu, Tự động hóa, AI, Cài đặt, Lịch sử, Tải xuống, Thông báo và Báo cáo được kiểm tra qua browser smoke, không thay đổi business logic.

## Kết quả thực tế

| Hạng mục | Kết quả |
| --- | --- |
| Python compile + unit/integration | PASS: 151 tests |
| JavaScript Vanilla | PASS: 9 test files |
| React TypeScript, lint, build | PASS |
| React tests | PASS: 15 tests / 9 files |
| Browser E2E local | PASS: 15 routes, đăng nhập/đăng xuất, Ctrl+K, lọc/lưu, theo dõi, automation, báo cáo, tải tài liệu, quyền admin, nhãn nút icon và màu skip link; không có JS exception hoặc asset 404 |
| Responsive/theme | PASS: 15 routes ở 1280×720, 1366×768, 1440×900, 1920×1080 và light mode 1366×768; mobile Sheet 390px; không tràn ngang toàn trang |
| Static/public HTTP | PASS: `/`, landing page SEO, `robots.txt`, `sitemap.xml`, `/api/health`; `/admin/sync` có guard và test deep link |
| Production bundle | Entry JS 110,85 kB gzip; CSS khoảng 16,5 kB gzip; route Search 11,15 kB gzip |
| Local database schema | PASS qua `server.production_check`; đây là SQLite local, không chứng minh migration PostgreSQL production |
| Docker image/container | CHƯA CHẠY: máy không có Docker |
| Cloud Run/GCS/Cloud SQL | CHƯA CHẠY: máy không có gcloud và production credentials |
| Production check | NOT READY: thiếu production config, URL HTTPS thật và truy cập GCS; debug disabled, React build, local schema đạt |

### Hiệu năng local

`python -m tools.load_test --levels 10,25,50,100 --requests 100` dùng SQLite tạm và HTTP handler thật; không gọi e-GP hay AI. 400/400 request trả 200, error rate 0. So với [baseline 4.9](PERFORMANCE_REPORT.md), p95 không cho thấy hồi quy nghiêm trọng; mẫu ngắn có nhiễu và không dự báo Cloud Run.

| Kết nối đồng thời | p50 | p95 | RPS | Lỗi |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 63,42 ms | 162,31 ms | 130,91 | 0 |
| 25 | 56,99 ms | 533,46 ms | 163,34 | 0 |
| 50 | 176,12 ms | 1.034,13 ms | 85,49 | 0 |
| 100 | 507,13 ms | 1.039,69 ms | 83,64 | 0 |

### Bảo mật và dữ liệu

Full Python suite gồm kiểm tra isolation nhiều user, quyền admin, ownership của automation/report/private document, CSRF, cấu hình production, migration và xử lý lỗi. Browser smoke xác nhận admin guard; React escape text theo mặc định. Đây là regression suite, **không phải pentest production**. `.env` và dữ liệu local được ignore; không đưa secret vào tài liệu release.

## Giới hạn và điều kiện còn thiếu

- Không có production URL nên canonical/sitemap cần `APP_BASE_URL` bằng URL HTTPS thực sau deploy; Google Search Console chưa thể xác minh hoặc submit sitemap thật.
- Production Cloud SQL cần backup trước migration, chạy migration job trên cùng image, xác nhận schema hiện hành và test `/ready` trên revision mới.
- GCS bucket private, Secret Manager, IAM, Cloud Logging/Monitoring và backup policy cần xác minh bằng credentials thật.
- Search job còn trạng thái tạm trong RAM instance. Deploy guide đặt `--max-instances 1`; không tự tăng scale-out khi chưa chuyển job sang storage dùng chung.
- Source e-GP, AI provider, tải/xuất dữ liệu lớn và soak/memory lâu dài chưa được đo trong production. OCR cho PDF scan chưa được bảo đảm.
- Một số bố cục React vẫn dựa trên legacy CSS bridge; đã QA light/dark và viewport mục tiêu, chưa xóa bridge để tránh rủi ro hồi quy.

## Phát hành và rollback

1. Hoàn tất các mục chưa chọn trong [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). Cài Docker/gcloud và cấp project, Cloud SQL, GCS, Secret Manager, service account phù hợp.
2. Chạy local `docker build -t muasamcong-pro:5.3.0 .`; thử image với cấu hình production-like, `/health`, `/ready`, `/login`, `/app/search` và static assets. Không dùng database production để thử tùy tiện.
3. Backup Cloud SQL; build image, chạy migration job cùng image, rồi deploy Cloud Run `muasamcong-pro` tại `asia-southeast1` theo [DEPLOYMENT.md](DEPLOYMENT.md). Chạy `python -m server.production_check` trong môi trường đã inject secret/DB/GCS; chỉ mở traffic khi in `PRODUCTION READY`.
4. Sau deploy, lấy URL bằng `gcloud run services describe muasamcong-pro --region asia-southeast1 --format='value(status.url)'`; đặt `APP_BASE_URL` đúng URL đó, kiểm tra SEO/robots/sitemap và các luồng đăng nhập → tra cứu → theo dõi → xuất. URL public hiện tại: **chưa có**.
5. Nếu revision lỗi, dùng `gcloud run revisions list --service muasamcong-pro --region asia-southeast1` rồi `gcloud run services update-traffic muasamcong-pro --region asia-southeast1 --to-revisions <LAST_GOOD_REVISION>=100`. Chỉ rollback code nếu schema tương thích; quy trình database nằm trong [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md).

**Release gate: FAIL cho public production** vì Docker/container, PostgreSQL/GCS, production check và Cloud Run smoke chưa chạy được. Local code/test gate: PASS. Không ghi nhận bug critical trong phạm vi local đã kiểm tra.
