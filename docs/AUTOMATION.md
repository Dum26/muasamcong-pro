# Automation Engine (MuaSamCong Pro)

Trang **Tự động hóa** trong `/app/automations` cho phép mỗi tài khoản tạo rule theo luồng **WHEN → IF → THEN**. Rule chạy trên dữ liệu gói thầu đã được đồng bộ vào hệ thống; nó không tự tìm dữ liệu mới từ nguồn bên ngoài. Người dùng có thể test bản nháp hoặc rule đã lưu mà không thay đổi dữ liệu, sau đó chạy thủ công hay đặt lịch mỗi giờ, 3 giờ, 6 giờ hoặc mỗi ngày.

Danh sách rule tìm theo tên và lọc theo trạng thái, trigger, lần chạy gần đây. Trang hiển thị thống kê riêng của tài khoản trong 14 ngày: số lượt chạy, gói khớp, lỗi và hành động thành công. Admin chỉ thấy số tổng hợp toàn hệ thống, thời gian chạy trung bình và top trigger; không thấy nội dung điều kiện riêng của người dùng.

Trigger hiện có: TBMT mới, tài liệu nguồn mới, gói khớp bộ lọc đã lưu, thông tin/trạng thái/giá thay đổi, sắp đóng thầu, có KQLCNT và chạy thủ công. Điều kiện hỗ trợ nhóm AND/OR lồng tối đa hai cấp, các trường văn bản, số, ngày, trạng thái đang theo dõi, tag và tên bộ lọc đã lưu. Trigger bộ lọc đã lưu đọc kết quả do job bộ lọc hiện tại ghi nhận và chỉ xét TBMT trong kho dữ liệu; cần chạy job `/internal/jobs/run-saved-searches` để cập nhật kết quả mới. Hành động: theo dõi/bỏ theo dõi, thêm/xóa tag, đặt ưu tiên/trạng thái nội bộ, tạo thông báo trong ứng dụng, thêm ghi chú mẫu và đưa gói vào hàng đợi kiểm tra tài liệu. Rule không gửi email, không gọi AI và không sửa dữ liệu gốc của gói thầu.

Mỗi hành động được ghi vào lịch sử sự kiện cùng lượt chạy; khóa chống trùng tránh thực hiện lại cùng hành động cho cùng gói và cùng sự kiện. Lịch sử và rule chỉ hiển thị với chủ tài khoản. Rule xóa được đánh dấu xóa mềm. Bộ lọc và hành động được kiểm tra lại ở backend; bản test không tạo side effect. Lượt chạy giới hạn 1.000 ứng viên để bảo vệ server. Kết quả trả về có cờ `truncated` và trạng thái `partial` nếu vượt giới hạn; với trigger TBMT mới, tài liệu mới và bộ lọc đã lưu có cursor để xử lý phần tiếp theo. Các trigger khác cần thu hẹp điều kiện nếu tập ứng viên quá lớn. Lịch chạy tự động cần scheduler bên ngoài; mở trình duyệt không kích hoạt lịch.

## Cloud Scheduler

Đặt `JOB_SECRET` trong Cloud Run bằng một chuỗi ngẫu nhiên tối thiểu 32 ký tự. Không commit secret vào repository. Tạo một Cloud Scheduler HTTP job gọi `POST https://<service>.run.app/internal/jobs/run-automations` định kỳ (chẳng hạn mỗi 5 phút), gửi header `X-Job-Secret: <JOB_SECRET>` và body `{}` với `Content-Type: application/json`. Endpoint từ chối request nếu secret thiếu hoặc sai. Nên dùng Secret Manager cho biến môi trường và header của job. Endpoint `/health` có thể dùng để kiểm tra service, không dùng để kích hoạt automation.

Ví dụ kiểm tra local (PowerShell):

```powershell
$env:JOB_SECRET = '<chuoi-ngau-nhien-it-nhat-32-ky-tu>'
python web_app.py
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8080/internal/jobs/run-automations' -Headers @{ 'X-Job-Secret' = $env:JOB_SECRET } -ContentType 'application/json' -Body '{}'
```

Rule mới bật sẽ có `next_run_at` theo tần suất chọn; rule thủ công không vào hàng đợi scheduler. Nếu dữ liệu nguồn không có nhà thầu trúng, rule KQLCNT không tự suy diễn kết quả. Trường ngày hạn đóng thầu được so với ngày tại Việt Nam.

Action `QUEUE_DOCUMENT_CHECK` dùng hàng đợi `refresh-tender` sẵn có và không tải tài liệu ngay trong lượt chạy rule; job `/internal/jobs/sync-tenders` xử lý hàng đợi theo giới hạn và retry hiện hành. Các hành động `ADD_TO_SAVED_VIEW`, `QUEUE_AI_ANALYSIS` và `EXPORT_TO_REPORT` chưa được bật trong bản này vì cần chính sách dữ liệu/quyền/chi phí riêng. Backend từ chối các action không nằm trong whitelist. Khi nhiều rule đặt mức ưu tiên cho cùng gói, mức cao nhất được giữ để kết quả không phụ thuộc thứ tự chạy.
