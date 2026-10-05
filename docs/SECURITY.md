# Kiểm tra bảo mật 5.0

- Auth: mật khẩu PBKDF2-HMAC SHA-256, session opaque lưu hash trong DB; inactive user bị từ chối. Admin API xác thực role; document/download dùng owner ID. Kiểm tra quyền bằng test và tài khoản thử của hai user.
- Production: bắt buộc PostgreSQL, secret mạnh, GCS; cookie HttpOnly/Secure/SameSite=Lax. Mutation dùng kiểm tra same-origin HTTPS `Origin` khi có cookie. CORS không mở wildcard. Nếu có client không gửi Origin, cần bổ sung CSRF token trước khi hỗ trợ client đó.
- SQL dùng SQLAlchemy bound parameters; upload giới hạn kích thước/đuôi/MIME theo endpoint, storage key và filename được kiểm tra; response 500 che traceback. Kiểm tra thêm file thực tế/antivirus theo nhu cầu vận hành.
- Headers: nosniff, Referrer-Policy, frame deny, Permissions-Policy, CSP. CSP còn `style-src 'unsafe-inline'` do CSS giao diện cũ; bỏ khi loại hết inline styles. Không nới script-src.
- Rate limit hiện lưu trong bộ nhớ **mỗi instance**; login có bucket theo email hash, các route khác theo owner/socket. Cloud Run nhiều instance cần Cloud Armor hoặc shared limiter để chặn lạm dụng xuyên instance. Search job cũng trong RAM, nên hiện giới hạn `max-instances=1`. Internal jobs dùng `JOB_SECRET`; tránh đưa secret vào log, URL hay tài liệu công khai.
- Log chỉ lưu route không query và request ID, tránh password/cookie/API key. GCS bucket private, Secret Manager và IAM cấp tối thiểu. Xem [sự cố](INCIDENT_RESPONSE.md) khi nghi lộ thông tin.
