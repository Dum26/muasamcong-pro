# AI Hồ sơ đấu thầu

Màn hình `/app/ai` cho phép tài khoản đã đăng nhập tải hồ sơ riêng, đọc văn bản trích xuất, chạy phân tích có nguồn và xuất kết quả XLSX/DOCX. Tài liệu có thể liên kết với mã TBMT/KHLCNT từ chi tiết gói thầu. File gốc, các đoạn văn bản, phân tích và lịch sử hỏi đáp đều gắn `user_id`; API trả 404 khi tài khoản khác truy cập ID đó. Xóa tài liệu xóa file gốc, văn bản, phân tích và hội thoại liên quan. Số liệu sử dụng AI giữ lại để quản trị token.

## Chạy local

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe web_main.py
```

Mặc định `AI_ENABLED=false`: tải lên, trích xuất, đọc và tải lại file vẫn hoạt động. File local ở `data/uploads`, metadata ở SQLite `data/muasamcong.db`; sao lưu cả hai. File hỗ trợ PDF có lớp chữ, DOCX, XLSX, XLS, TXT, CSV; mặc định tối đa 10 MB (`MAX_UPLOAD_MB`, 1–50). File lớn hơn `INLINE_EXTRACTION_MAX_MB` (mặc định 3 MB) ở trạng thái chờ job để tránh giữ request HTTP lâu. PDF chỉ có ảnh được đánh dấu nghi là scan; OCR **chưa tích hợp**, nên không thể phân tích nội dung ảnh. Upload kiểm tra extension, MIME và cấu trúc file; không thay thế phần mềm quét mã độc chuyên dụng.

Để bật OpenAI, đặt các biến môi trường ở máy chủ, không trong frontend:

```text
AI_ENABLED=true
AI_PROVIDER=openai
AI_MODEL=<MODEL_DO_BAN_CHON>
OPENAI_API_KEY=<SECRET_CHI_TREN_SERVER>
```

Ứng dụng gửi tối đa 14 đoạn chứng cứ được chọn bằng từ khóa cho mỗi tài liệu, yêu cầu JSON có source ID và kiểm tra ID trước khi hiển thị. Người dùng có thể bấm chip nguồn để về đúng trang PDF, mục DOCX hoặc dòng Excel đã trích xuất. Đây là hỗ trợ đọc tài liệu; kết quả cần đối chiếu hồ sơ gốc. `store:false` được gửi trong Responses API. Không có key/model thì API trả 503 rõ ràng; không có kết quả AI giả. Kết quả cùng tài liệu, tác vụ, câu hỏi và model được lưu và tái dùng; bấm **Phân tích lại** để gọi mới. Khi trích xuất lại tài liệu, cache cũ không được dùng.

Số token thực do provider trả về nằm trong `ai_usage` và hiển thị tại `/admin`. Ước tính chi phí để trống mặc định; chỉ có giá trị khi cấu hình `AI_INPUT_PRICE_PER_1M` và `AI_OUTPUT_PRICE_PER_1M` theo cùng một loại tiền. Các mức giá này do quản trị viên cung cấp, không tự suy đoán.

## Cloud Run

Production yêu cầu PostgreSQL và `STORAGE_BACKEND=gcs,GCS_BUCKET=<PRIVATE_BUCKET>`. Bucket phải riêng tư; service account Cloud Run cần quyền đọc/ghi/xóa object. Cấp `OPENAI_API_KEY` qua Secret Manager, chẳng hạn thêm `OPENAI_API_KEY=muasamcong-openai-key:latest` vào `--set-secrets`; thêm `AI_ENABLED=true,AI_PROVIDER=openai,AI_MODEL=<MODEL>` vào `--set-env-vars`. Chỉ bật sau khi có key và model hợp lệ; không đưa key vào Git hoặc mã JS.

Route `POST /internal/jobs/process-document` có `X-Job-Secret` xử lý một số tài liệu còn chờ; giao diện tự gọi trích xuất ngay cho file nhỏ và polling trạng thái file lớn. Cấu hình Cloud Scheduler gọi endpoint này theo lịch ngắn (ví dụ mỗi phút) trước khi cho phép upload file lớn trên production. Khi tải nhiều file lớn, nên chuyển tác vụ dài sang Cloud Tasks để tránh giới hạn thời gian của HTTP request Cloud Run. Chưa có Cloud Tasks tự động, OCR hoặc quét virus. Không thể kiểm thử live OpenAI/GCS từ môi trường này khi chưa có credential tương ứng.

Kiểm thử: `.venv\Scripts\python.exe -m unittest tests.test_documents tests.test_document_http`; toàn bộ suite dùng `-m unittest discover -s tests -p "test_*.py"` và `npm test`.
