# MuaSamCong Pro 5.3 — triển khai Cloud Run

Ứng dụng giữ Python backend; Docker image build React 5.3 và phục vụ giao diện này tại `/app` (`REACT_FRONTEND_ENABLED=1`). Các trang SEO public vẫn là HTML, giao diện Vanilla cũ còn ở `/legacy` để kiểm tra tương thích. Cloud Run phục vụ HTTPS; PostgreSQL Cloud SQL giữ dữ liệu, bucket GCS riêng tư giữ tài liệu. Cloud Run filesystem chỉ là tạm thời. `ENV=production` yêu cầu PostgreSQL, `SESSION_SECRET`/`JOB_SECRET` dài tối thiểu 32 ký tự, `STORAGE_BACKEND=gcs` và schema hiện hành. Server **không tự migrate** trong production.

## Trước khi triển khai

Từ thư mục project, chạy `python tools/predeploy_check.py` (Python tests, JS tests, CSS, syntax và smoke local), `node tools/smoke_react_browser.cjs` nếu có Chrome, rồi `docker build -t muasamcong-pro:5.3.0 .` nếu có Docker. Local: build `frontend/` và đặt `REACT_FRONTEND_ENABLED=1` trước khi chạy `python web_app.py`; `/health` và `/ready` phải trả 200. Xem [checklist phát hành](RELEASE_CHECKLIST.md). Không đưa `.env`, database local hoặc khóa vào image.

Các lệnh dưới dùng PowerShell. Thay placeholder bằng tài nguyên thật, chọn một Cloud SQL PostgreSQL instance và một bucket GCS trong `asia-southeast1`. Cấu hình Cloud SQL automated backup hàng ngày, giữ ít nhất 14 ngày, bật point-in-time recovery nếu gói hỗ trợ. Bật uniform bucket-level access, public access prevention và object versioning/lifecycle phù hợp. Tạo service account riêng cho Cloud Run, cấp Cloud SQL Client, Secret Manager Secret Accessor trên ba secret, Storage Object Admin trên bucket và quyền đọc metadata bucket nếu muốn kiểm tra GCS bằng `/api/admin/production-status` hoặc `production_check`. Không cấp quyền công khai cho bucket.

```powershell
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com storage.googleapis.com artifactregistry.googleapis.com
gcloud config set run/region asia-southeast1
```

Tạo ba Secret Manager secrets: `muasamcong-database-url`, `muasamcong-session-secret`, `muasamcong-job-secret`. Giá trị DB URL dùng dạng `postgresql+psycopg://USER:PERCENT_ENCODED_PASSWORD@/DATABASE?host=/cloudsql/PROJECT_ID:asia-southeast1:INSTANCE`; URL-encode mật khẩu. Tạo phiên bản secret bằng console hoặc nguồn bí mật an toàn; tránh gõ giá trị vào terminal history. Service account phải đọc được các phiên bản đã ghim. Cloud Run `--set-secrets` ánh xạ ba giá trị vào `DATABASE_URL`, `SESSION_SECRET`, `JOB_SECRET`. Nếu bật AI, thêm `OPENAI_API_KEY` từ Secret Manager và cấu hình `AI_ENABLED=true,AI_PROVIDER=openai,AI_MODEL=<MODEL>`.

## Build, migration, deploy

Cloud Run job migration dùng **cùng image** với web. Trước migration, tạo on-demand backup (`gcloud sql backups create --instance=<INSTANCE>`) và kiểm tra backup đã thành công. Migration 5.0 chỉ thêm schema; không xóa bảng. Cloud Run service khởi động sẽ từ chối schema cũ, nên migration phải chạy trước deploy. Nếu phiên bản cũ không tương thích schema mới, tạm dừng traffic/scheduler trong cửa sổ bảo trì.

```powershell
gcloud artifacts repositories create muasamcong --repository-format=docker --location=asia-southeast1
$IMAGE = "asia-southeast1-docker.pkg.dev/<PROJECT_ID>/muasamcong/muasamcong-pro:5.3.0"
gcloud builds submit . --tag $IMAGE
gcloud run jobs deploy muasamcong-migrate --image $IMAGE --region asia-southeast1 --service-account <SERVICE_ACCOUNT_EMAIL> --set-cloudsql-instances <PROJECT_ID>:asia-southeast1:<INSTANCE> --set-secrets DATABASE_URL=muasamcong-database-url:<VERSION>,SESSION_SECRET=muasamcong-session-secret:<VERSION>,JOB_SECRET=muasamcong-job-secret:<VERSION> --set-env-vars ENV=production,STORAGE_BACKEND=gcs,GCS_BUCKET=<PRIVATE_BUCKET> --command /opt/venv/bin/python --args=-m,server.database,migrate --max-retries 0
gcloud run jobs execute muasamcong-migrate --region asia-southeast1 --wait
gcloud run deploy muasamcong-pro --image $IMAGE --region asia-southeast1 --allow-unauthenticated --service-account <SERVICE_ACCOUNT_EMAIL> --add-cloudsql-instances <PROJECT_ID>:asia-southeast1:<INSTANCE> --set-secrets DATABASE_URL=muasamcong-database-url:<VERSION>,SESSION_SECRET=muasamcong-session-secret:<VERSION>,JOB_SECRET=muasamcong-job-secret:<VERSION> --set-env-vars ENV=production,LOG_LEVEL=INFO,STORAGE_BACKEND=gcs,GCS_BUCKET=<PRIVATE_BUCKET> --memory 1Gi --concurrency 10 --max-instances 1
gcloud run services describe muasamcong-pro --region asia-southeast1 --format='value(status.url)'
```

`--max-instances 1` là giới hạn hiện tại vì search job đang giữ trạng thái trong RAM của instance; tăng số instance trước khi đưa job đó vào DB/queue sẽ làm mất kết quả khi poll trúng instance khác. Một instance vẫn phục vụ nhiều user qua ThreadingHTTPServer, concurrency 10. Pool mặc định tối đa 5 kết nối app; cộng migration/job workers khi so quota Cloud SQL. Có thể dùng `gcloud run deploy muasamcong-pro --source . ...` với cùng các cờ sau khi schema đã migrate, nhưng build image một lần giúp web và migration dùng đúng một bản. Sau khi có URL `https://…run.app`, đặt `APP_BASE_URL` bằng URL thật qua `gcloud run services update muasamcong-pro --region asia-southeast1 --update-env-vars APP_BASE_URL=<URL_HTTPS_THAT>`; chạy `python -m server.production_check` trong môi trường production đã inject secrets/DB/GCS. `APP_BASE_URL` dùng cho canonical/sitemap, không dùng domain giả.

Cloud Scheduler gọi các `/internal/jobs/...` theo [SEO_DEPLOY.md](SEO_DEPLOY.md) bằng secret nội bộ. Hạn chế người được xem/sửa job; không ghi `JOB_SECRET` trong file cấu hình công khai. In-memory search jobs/rate limits là phạm vi từng instance; dùng Cloud Armor hoặc Redis khi traffic tăng. Không dựa vào filesystem Cloud Run cho download history hay hồ sơ.

## Xác nhận sau deploy

Mở `/`, `/health`, `/ready`, `/version`, `/robots.txt`, `/sitemap.xml`; đăng nhập và kiểm tra search, chi tiết gói, theo dõi, tài liệu, phân tích, automation list, export không phá dữ liệu. `/ready` phải 200; `/api/admin/production-status` chỉ admin xem được. Kiểm tra cookie Secure/HttpOnly, 5xx và latency trong Cloud Logging/Monitoring; tạo alert cho 5xx, p95 latency, Cloud SQL connections/CPU, Cloud SQL backup failure và GCS errors. Xem [sự cố](INCIDENT_RESPONSE.md).

Rollback revision: `gcloud run revisions list --service muasamcong-pro --region asia-southeast1`, sau đó `gcloud run services update-traffic muasamcong-pro --region asia-southeast1 --to-revisions <LAST_GOOD_REVISION>=100`. Chỉ rollback code trực tiếp khi schema mới vẫn tương thích code cũ; nếu không, dùng [quy trình khôi phục](DISASTER_RECOVERY.md). URL service giữ nguyên giữa các revision. Với domain riêng về sau, ánh xạ domain thật và cập nhật `APP_BASE_URL`; Google Search Console: add property, verify, submit `/sitemap.xml`, URL Inspection và request indexing.
