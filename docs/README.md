# Tài liệu

- [FINAL_RELEASE_5_3.md](FINAL_RELEASE_5_3.md): trạng thái QA và release gate 5.3.
- [RELEASE_NOTES_5_3.md](RELEASE_NOTES_5_3.md): thay đổi, giới hạn và ghi chú triển khai.
- [HUONG_DAN_PRO.txt](HUONG_DAN_PRO.txt): hướng dẫn cũ, giữ để tham khảo.
- `HUONG_DAN.txt`: ghi chú cho giao diện desktop cũ; shortcut nằm ở thư mục gốc project.
- `HUONG_DAN_CHIA_SE.txt`: hướng dẫn chia sẻ của phiên bản trước, lưu lại để tham khảo.
- [BI_REPORTING.md](BI_REPORTING.md): phân tích BI, Report Builder, dashboard riêng, API và giới hạn dữ liệu.
- [DEPLOYMENT.md](DEPLOYMENT.md): build, migration và deploy production trên Cloud Run.
- [FRONTEND_MIGRATION_5_1.md](FRONTEND_MIGRATION_5_1.md): mapping Vanilla → React và trạng thái parity thực tế.
- [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md): backup, restore, rollback.
- [FRONTEND_DESIGN_SYSTEM_5_2.md](FRONTEND_DESIGN_SYSTEM_5_2.md): nền tảng component của giao diện React.
- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), [SECURITY.md](SECURITY.md), [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md): kiểm tra và vận hành production.

Ứng dụng web chạy local bằng `web_app.py` hoặc `web_main.py`; build React trong `frontend/dist` và đặt `REACT_FRONTEND_ENABLED=1` để xem giao diện 5.3. Xem [README gốc](../README.md) để cài và chạy.

## Cấu trúc project

- Thư mục gốc: file khởi chạy `web_main.py`, `main.py`, `app.py`, Dockerfile và cấu hình build.
- `server/`: đăng nhập, database, API tài liệu, AI, SEO và các job nền.
- `frontend/`: React/TypeScript/Vite, Tailwind, shadcn/ui và Lucide cho `/app`.
- `web/`: HTML/CSS/JavaScript cho trang SEO public và `/legacy`.
- `tests/`: kiểm thử Python và JavaScript; `tools/`: công cụ quản trị.
- `docs/`: hướng dẫn; `legacy/`: tài liệu/code phiên bản cũ.
- `data/`: dữ liệu local; `.venv/`, `node_modules/`, `build/`, `dist/`: môi trường và sản phẩm build.

VS Code ẩn các thư mục tạo tự động và `data/` trong Explorer để dễ tập trung vào source; các file vẫn còn nguyên trên đĩa. Có thể bỏ ẩn trong `.vscode/settings.json` khi cần sao lưu hoặc kiểm tra dữ liệu.

## Giao diện web

Giao diện ứng dụng chính dùng React/TypeScript trong `frontend/`. Python phục vụ bản build tĩnh tại `/app`, vẫn giữ các API hiện có. `web/` tiếp tục phục vụ trang SEO public và giao diện Vanilla cũ tại `/legacy`; CSS Tailwind và Lucide trong `web/` được giữ cho các trang đó và bản EXE.

- `npm ci --prefix frontend`: cài gói React đúng phiên bản từ lockfile.
- `npm --prefix frontend run build`: typecheck và build React production.
- `npm ci`: cài dependency cho CSS/kiểm thử giao diện Vanilla còn dùng.
- `npm run dev:css`: theo dõi và build CSS khi sửa giao diện.
- `npm run build:css`: build CSS production trước khi đóng gói.
- `npm test`: kiểm thử JavaScript.
- `.venv/Scripts/python.exe tools/predeploy_check.py`: kiểm tra Python, JavaScript, React, build và HTTP local.
- `.venv/Scripts/pyinstaller.exe --noconfirm MuaSamCongPro.spec`: cập nhật một file `dist/MuaSamCongPro.exe`.

Các file `web/tailwind.css`, `web/ui-system.css`, `web/ui-system.js` và
`web/vendor/lucide.min.js` được đóng gói qua thư mục `web` trong spec hiện tại.

## Tự động hóa

Xem [hướng dẫn Automation Engine](AUTOMATION.md) để tạo rule, test không làm thay đổi dữ liệu và cấu hình Cloud Scheduler.

Xem [Data Sync Engine 4.5](DATA_SYNC.md) để vận hành source registry, sync run, checkpoint, retry và Cloud Scheduler.
