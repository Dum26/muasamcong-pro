# MuaSamCong Pro: local và Cloud Run

Ứng dụng giữ Python `ThreadingHTTPServer` và frontend HTML/CSS/JS. `/` và `/loc-du-lieu-mua-sam-cong` là trang công khai; `/app`, API dữ liệu người dùng và `/admin` cần đăng nhập. `robots.txt` và `sitemap.xml` chỉ dẫn crawler đến nội dung công khai. `SITE_URL` có thể để trống trên `run.app`: canonical URL được tạo từ host HTTPS đã kiểm tra. Khi dùng domain riêng, đặt `SITE_URL` thành origin HTTPS thực tế.

## Chạy local

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe web_main.py
```

Nếu không đặt `DATABASE_URL`, local dùng SQLite ở `data/muasamcong.db`. Server tự nâng schema lên version 3, không xóa dữ liệu khi khởi động lại. File tài liệu local nằm trong `data/uploads` và cần sao lưu cùng database. Đăng ký tài khoản ở `/register`. Để cấp quyền admin cho tài khoản đã tạo: `.venv\Scripts\python.exe tools\promote_admin.py your-email@example.com`. File JSON và localStorage cũ chỉ được nhập khi người dùng đăng nhập và bấm **Nhập dữ liệu cũ**; hãy giữ bản sao dữ liệu cũ trước khi chuyển.

`SQLAlchemy` quản lý schema/transaction cho SQLite và PostgreSQL; `psycopg` là driver PostgreSQL. `requests` và `openpyxl` vẫn phục vụ tra cứu e-GP và Excel. Khi schema phát triển, thêm migration version mới trong `server/database.py`; không sửa migration đã chạy hoặc xóa bảng người dùng.

Chạy kiểm tra: `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`, `npm test` và `.venv\Scripts\python.exe tools\smoke_cloud_run.py`. Docker, nếu có: `docker build -t muasamcong-pro .`. Container production **bắt buộc** có PostgreSQL `DATABASE_URL`, `SESSION_SECRET` dài ít nhất 32 ký tự, `STORAGE_BACKEND=gcs` và `GCS_BUCKET`; lệnh `docker run` thiếu các biến đó sẽ dừng có chủ đích. Không dùng SQLite hoặc filesystem Cloud Run để lưu dữ liệu tài khoản và hồ sơ.

## Triển khai Cloud Run

Các lệnh sau cần một Google Cloud project thật, billing, `gcloud` và quyền tạo Cloud SQL, Cloud Storage, Secret Manager, Cloud Run, Cloud Scheduler. Tạo Cloud SQL PostgreSQL trong `asia-southeast1`, database và database user riêng; ghi lại connection name dạng `PROJECT_ID:asia-southeast1:INSTANCE`. Tạo bucket Cloud Storage riêng tư trong cùng region, không bật public access; cấp cho service account Cloud Run quyền đọc/ghi/xóa object trong bucket. Cấp Cloud SQL Client và Secret Manager Secret Accessor cho cùng service account. Tạo ba secret trong Secret Manager:

- `muasamcong-database-url`: `postgresql+psycopg://USER:PERCENT_ENCODED_PASSWORD@/DATABASE?host=/cloudsql/PROJECT_ID:asia-southeast1:INSTANCE`
- `muasamcong-session-secret`: chuỗi ngẫu nhiên ít nhất 32 ký tự.
- `muasamcong-job-secret`: chuỗi ngẫu nhiên ít nhất 32 ký tự, khác session secret.

Không đặt mật khẩu/secret trong source, `.env.example`, lịch sử shell hoặc biến `--set-env-vars`. Với Cloud SQL public IP, cấu hình connector/socket Cloud Run phù hợp; với private IP cần VPC connector tương ứng. Sau khi cấp quyền, triển khai từ thư mục project:

```powershell
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com
gcloud run deploy muasamcong-pro --source . --region asia-southeast1 --allow-unauthenticated --add-cloudsql-instances <PROJECT_ID>:asia-southeast1:<INSTANCE> --set-secrets DATABASE_URL=muasamcong-database-url:latest,SESSION_SECRET=muasamcong-session-secret:latest,JOB_SECRET=muasamcong-job-secret:latest --set-env-vars ENV=production,LOG_LEVEL=INFO,STORAGE_BACKEND=gcs,GCS_BUCKET=<PRIVATE_BUCKET> --memory 1Gi --concurrency 10 --max-instances 1
gcloud run services describe muasamcong-pro --region asia-southeast1 --format="value(status.url)"
```

`--max-instances 1` hạn chế số kết nối Cloud SQL và phù hợp cache/job trong tiến trình hiện tại; nó không bảo đảm chỉ có một tiến trình trong lúc thay revision. Các tác vụ người dùng đã lưu trong PostgreSQL. Kết quả tra cứu đang chạy vẫn chỉ nằm trong RAM và có thể mất khi instance thay đổi; người dùng có thể chạy lại truy vấn đã lưu. Download Excel đã lưu được giữ 24 giờ trong PostgreSQL (giới hạn 25 MB mỗi file); Scheduler cleanup xóa file hết hạn. Cloud SQL, Cloud Run và Scheduler có thể phát sinh chi phí.

Sau khi tài khoản quản trị đầu tiên tự đăng ký, chạy `tools/promote_admin.py` từ máy quản trị với `DATABASE_URL` kết nối đến đúng Cloud SQL (ví dụ qua Cloud SQL Auth Proxy và tài khoản database có quyền cập nhật `users`). Không cấp admin tự động theo email trong biến môi trường: ai đăng ký email trước có thể chiếm quyền. Sao lưu Cloud SQL trước khi nâng version schema.

Các endpoint job `POST /internal/jobs/check-followed-tenders`, `/internal/jobs/run-saved-searches`, `/internal/jobs/cleanup-downloads`, `/internal/jobs/process-document` yêu cầu header `X-Job-Secret` khớp `JOB_SECRET`, `Content-Type: application/json` và body `{}`. Tạo Cloud Scheduler HTTP jobs bằng tài khoản quản trị, đặt lịch `0 8,12,17 * * *` với timezone `Asia/Bangkok` cho hai job kiểm tra, `0 2 * * *` cho cleanup, và lịch ngắn như `* * * * *` cho `process-document` khi cho phép file lớn. Chỉ gửi secret qua cấu hình job có quyền quản trị giới hạn; đừng ghi giá trị thật vào tài liệu hoặc shell history. Job có giới hạn số gói mỗi lần chạy; theo dõi bảng `job_runs` ở `/admin` và điều chỉnh cadence theo tải thực tế. Chưa tạo Scheduler tự động vì project/credential chưa được cung cấp. Giao diện xử lý ngay file nhỏ; file lớn chờ job và được polling trạng thái. Với hồ sơ lớn/nhiều người dùng, cấu hình Cloud Tasks cho xử lý ngoài request như một bước triển khai tiếp theo.

Kiểm tra HTTPS `/health`, `/`, `/loc-du-lieu-mua-sam-cong`, `/robots.txt`, `/sitemap.xml`; đăng ký, đăng nhập, tra cứu, theo dõi, xuất/tải lại Excel và kiểm tra cách ly giữa hai tài khoản. Trang SEO công khai không yêu cầu login. Trong Google Search Console: thêm property, xác minh domain hoặc URL prefix của `run.app`, submit `/sitemap.xml`, dùng URL Inspection và Request indexing cho các trang công khai. Không yêu cầu index `/app` hoặc API.
# Lưu ý cho bản 5.0

Quy trình production hiện hành nằm ở [DEPLOYMENT.md](DEPLOYMENT.md). Phải backup và chạy `python -m server.database migrate` bằng Cloud Run job trước khi deploy service; không dùng lệnh deploy cũ ở trên với database chưa migrate.
