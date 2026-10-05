# Ứng phó sự cố

Ghi nhận thời điểm, revision, request ID và phạm vi user ảnh hưởng. Không dán secret, cookie hay dữ liệu hồ sơ vào ticket/log. Phân công người chỉ huy và lưu các bước đã làm.

| Sự cố | Hành động đầu tiên | Khôi phục/xác nhận |
| --- | --- | --- |
| Cloud SQL ngừng | Kiểm tra Cloud SQL status, connections và `/ready`; tạm dừng jobs ghi | Failover/restore theo [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md), xác nhận schema và dữ liệu |
| Nguồn e-GP ngừng | Xem source health, circuit, log; giảm nhịp scheduler | Giữ dữ liệu cache, thử lại khi nguồn hồi; kiểm tra sync backlog |
| AI provider ngừng | Xem lỗi provider/quota; tắt `AI_ENABLED` nếu cần | Chức năng lõi vẫn chạy; bật lại sau khi kiểm tra key/quota |
| GCS ngừng | Kiểm tra IAM/bucket và download; dừng job tài liệu | Khôi phục IAM/object, xác nhận owner và checksum |
| Lộ credential | Thu hồi quyền, rotate secret/key và audit truy cập | Redeploy service/job, kiểm tra session/DB/scheduler |
| Deploy lỗi | So `/version`, 5xx, p95; chuyển về revision tốt | Kiểm tra tương thích schema trước rollback |

Sau khắc phục: chạy smoke test, theo dõi ít nhất một chu kỳ sync, ghi nguyên nhân và biện pháp phòng ngừa. Cloud Monitoring alerts phải được cấu hình trong project thật; code repo không tự tạo chúng.
