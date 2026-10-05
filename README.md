# MuaSamCong Pro 5.3

Bàn làm việc đấu thầu: tra cứu TBMT/KHLCNT, xem chi tiết, theo dõi thay đổi, quản lý tài liệu, tự động hóa, phân tích và xuất dữ liệu. Các trang public tại `/` và `/loc-du-lieu-mua-sam-cong` phục vụ SEO; ứng dụng đăng nhập nằm tại `/app`.

## Kiến trúc

- `frontend/`: React 19, TypeScript, Vite, Tailwind CSS 4, shadcn/ui và Lucide React. Build tĩnh được Python phục vụ tại `/app`.
- `web/`: trang SEO public và giao diện Vanilla cũ tại `/legacy`.
- `web_app.py`, `server/`, `app.py`: Python HTTP/API, đăng nhập, tra cứu, đồng bộ, automation, tài liệu và phân tích.
- Database: SQLite khi chạy local; PostgreSQL khi chạy production. Tài liệu production lưu ở GCS.

## Chạy local (PowerShell)

```powershell
cd E:\muasamcongtool
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
npm ci --prefix frontend
npm --prefix frontend run build
$env:REACT_FRONTEND_ENABLED = '1'
.\.venv\Scripts\python.exe web_app.py
```

Server in URL local và mở `/app` khi chạy tương tác. Lần đầu có thể đăng ký tài khoản tại `/register`. Cấu hình mẫu nằm trong [.env.example](.env.example); không đưa secret thật vào Git.

## Kiểm thử và build

```powershell
.\.venv\Scripts\python.exe tools\predeploy_check.py
node tools\smoke_react_browser.cjs
docker build -t muasamcong-pro:5.3.0 .
```

Browser smoke cần Chrome và `.venv`. Lệnh Docker chỉ chạy khi đã cài Docker; môi trường phát triển hiện tại chưa có Docker. Production cần cấu hình Cloud SQL, GCS và Secret Manager trước khi chạy migration và deploy. Xem [quy trình Cloud Run](docs/DEPLOYMENT.md), [release gate 5.3](docs/FINAL_RELEASE_5_3.md) và [hướng dẫn tài liệu](docs/README.md).
