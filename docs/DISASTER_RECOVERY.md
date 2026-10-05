# Khôi phục sự cố

Mục tiêu vận hành ban đầu: backup Cloud SQL hàng ngày, giữ tối thiểu 14 ngày; bật point-in-time recovery nếu khả dụng. Kiểm tra restore vào **instance thử nghiệm riêng** ít nhất mỗi quý và trước migration lớn. Ghi lại thời điểm backup, schema version và revision ứng dụng. Cloud SQL và GCS là hai nguồn dữ liệu cần bảo vệ; image có thể build lại.

1. Ngừng scheduler và các job ghi dữ liệu; ghi thời điểm bắt đầu sự cố. Không chạy migration/restore lên DB đang phục vụ khi chưa xác định phạm vi mất dữ liệu.
2. Xem `gcloud sql backups list --instance=<INSTANCE>` và Cloud SQL console. Tạo bản backup thủ công trước thao tác sửa chữa nếu DB còn truy cập được: `gcloud sql backups create --instance=<INSTANCE>`. Khôi phục backup hoặc point-in-time vào instance **mới**, kiểm tra schema và số bản ghi/tài khoản/tài liệu. Sau đó đổi Secret Manager version của `DATABASE_URL` sang instance mới và deploy revision mới. Không ghi DB password vào lệnh/log.
3. Tài liệu: bật GCS object versioning/retention trước khi có sự cố. Khi xóa nhầm, khôi phục đúng generation từ GCS console/CLI; đối chiếu `storage_key`, quyền chủ sở hữu trong DB và checksum. Không chuyển bucket sang public. DB restore và GCS restore phải được đối chiếu cùng mốc thời gian; document record không có object cần xử lý riêng.
4. Lộ secret: tạo version mới cho `SESSION_SECRET`, `JOB_SECRET`, DB password và AI key liên quan; cập nhật Cloud Run service/job/scheduler, thu hồi version cũ. Đổi `SESSION_SECRET` làm phiên đăng nhập cũ mất hiệu lực; thông báo người dùng đăng nhập lại. Kiểm tra log truy cập và quyền IAM.
5. Deploy lỗi: chuyển traffic về revision tốt gần nhất bằng `gcloud run services update-traffic muasamcong-pro --region asia-southeast1 --to-revisions <REVISION>=100`. Không rollback code khi migration đã phá tương thích; khôi phục DB thử nghiệm trước khi quyết định.
6. Xác nhận `/health`, `/ready`, `/version`, đăng nhập, search, watchlist, document list/download, job và GCS. Theo dõi 5xx, latency, queue, source health trong tối thiểu một chu kỳ sync. Chỉ bật lại scheduler khi dữ liệu ổn định.

Tham khảo lệnh và tài nguyên trong [DEPLOYMENT.md](DEPLOYMENT.md). Cloud SQL backups cần được cấu hình/kiểm tra trên project thật; repo không thể tự đảm bảo một backup đã tồn tại.
