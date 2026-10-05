# Data Sync Engine 4.5

## Reliability update

- `server/source/request_manager.py` là lớp HTTP dùng chung cho e-GP: timeout connect/read, retry lỗi tạm thời với backoff và jitter, tôn trọng `Retry-After`, rate limit qua PostgreSQL trên Cloud Run (trong tiến trình khi chạy local), circuit breaker và request dedup trong tiến trình.
- Cache in-memory có TTL riêng cho search, chi tiết và KQLCNT. Force refresh bỏ qua cache; khi nguồn lỗi có thể trả cache cũ kèm `stale=true`. Cache không chứa trạng thái riêng của từng tài khoản.
- `server/source/errors.py` phân biệt lỗi timeout, kết nối, giới hạn tốc độ, từ chối, máy chủ, JSON/schema và không tìm thấy. Parser/search giữ nguyên logic hiện tại.
- Migration v8–v10 thêm priority, max attempts và lock owner cho `background_jobs`, freshness metadata cho `tenders`, bảng `source_health_events`, lịch đặt lượt request chung và index hàng đợi theo loại job. Migration chỉ thêm cột/bảng/index, không xóa dữ liệu cũ.
- Admin Sync Center hiển thị sức khỏe nguồn, cache hit, request lỗi, job gần đây và tiến độ run. Admin có thể retry, hủy job đang chờ, đưa một mã TBMT vào queue và dọn job completed cũ. Job còn liên kết với lịch sử run được giữ lại.
- Cloud Scheduler có thể gọi `POST /internal/jobs/run-sync` hoặc alias cũ `/internal/jobs/run-data-sync` với `X-Job-Secret`.

Trên Cloud Run, PostgreSQL chia sẻ lượt rate limit và hàng đợi giữa các instance; enqueue dùng khóa giao dịch để tránh trùng job. Cache, request dedup, circuit breaker và rolling health vẫn theo từng tiến trình; số đo nguồn trong UI phản ánh instance xử lý request. Nếu cần số đo tổng hợp giữa nhiều instance, bổ sung kho metrics tập trung.

Data Sync Engine điều phối việc làm mới dữ liệu TBMT công khai từ e‑GP trên hàng đợi bền vững. Engine tái sử dụng adapter nguồn, chuẩn hóa, snapshot, change tracking và upsert hiện có; nó không thay đổi cách dữ liệu đấu thầu được diễn giải.

## Kiến trúc

- `sync_sources`: registry nguồn và lịch chạy. Cấu hình chỉ chứa thông số không nhạy cảm.
- `sync_runs`: một lượt đồng bộ, nguồn kích hoạt, chế độ, tổng số phát hiện/xếp hàng/thành công/lỗi và thời gian hoàn tất.
- `sync_run_items`: liên kết từng mã TBMT với `background_jobs`, trạng thái, số lần thử và lỗi thân thiện.
- `sync_checkpoints`: checkpoint cuối cùng của từng nguồn/stream.
- `background_jobs`: queue cho refresh TBMT, gói đang theo dõi và bộ lọc đã lưu; khóa claim nguyên tử, tối đa ba lần thử và exponential backoff.

Các chế độ hiện có:

- `stale`: lấy các TBMT chưa đồng bộ hoặc cũ hơn ngưỡng nguồn (mặc định 6 giờ).
- `failed`: chạy lại các TBMT đang có `sync_error`.
- `codes`: danh sách mã TBMT cụ thể, loại trùng trước khi xếp hàng.

Chỉ admin có thể xem hoặc tạo sync run qua `/api/data-sync`. Một nguồn chỉ có một run `queued/running` tại một thời điểm; yêu cầu trùng trả lại run đang hoạt động. Dữ liệu nguồn là dữ liệu công khai dùng chung, còn người khởi tạo thủ công được ghi vào audit log.

Admin có thể bật/tạm dừng nguồn tại `/api/data-sync/sources/{id}/enable|pause`. Các thao tác Data Sync từ UI bị giới hạn 10 request/phút cho mỗi tài khoản; endpoint Scheduler dùng secret riêng và không dùng rate limit người dùng.

## API

- `GET /api/data-sync`: nguồn, run gần đây, checkpoint và số lượng queue theo trạng thái.
- `GET /api/data-sync/runs/{id}`: chi tiết run và tối đa 500 item.
- `POST /api/data-sync/runs`: tạo run với `mode`, `limit`, và `codes` khi mode là `codes`.
- `POST /api/data-sync/process`: xử lý một batch queue và reconcile run.
- `POST /api/data-sync/runs/{id}/process`: xử lý rồi reconcile một run.
- `POST /api/data-sync/runs/{id}/retry`: tạo run mới từ các item lỗi của run cũ.

## Cloud Scheduler

Scheduler gọi:

```text
POST https://<service>.run.app/internal/jobs/run-data-sync
Content-Type: application/json
X-Job-Secret: <JOB_SECRET tối thiểu 32 ký tự>

{}
```

Endpoint dùng cùng cơ chế constant-time secret check với các background job hiện tại. Nên chạy mỗi 5 phút; `sync_sources.next_run_at` quyết định có cần tạo run mới hay chỉ xử lý queue đang chờ. Không chạy polling thread trong tiến trình Cloud Run.

Run rỗng vẫn cập nhật checkpoint và `next_run_at`, tránh tạo run liên tục. Job bị gián đoạn quá 10 phút được đưa về retry; sau ba lần lỗi sẽ chuyển `failed`. Retry run chỉ lấy lại item đã lỗi. Lỗi kỹ thuật được ghi server log; API/UI chỉ trả thông báo giới hạn 300 ký tự.

## Giới hạn hiện tại

Source registry hiện bật adapter `egp-public`. Engine 4.5 làm mới các mã đã biết hoặc mã admin chỉ định; việc khám phá TBMT mới trên diện rộng vẫn đi qua luồng tìm kiếm/saved search hiện có để tránh quét không kiểm soát nguồn e‑GP. Không lưu credential nguồn trong database.
