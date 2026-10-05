# MuaSamCong Pro 5.3 — release notes

Ngày chuẩn bị: 01/10/2026. 5.3 hoàn thiện giao diện và kiểm thử của roadmap hiện tại; không thay đổi kiến trúc database hay API nghiệp vụ.

## Sản phẩm

- Tra cứu TBMT/KHLCNT, lọc ngày và điều kiện, mở chi tiết, theo dõi gói, xem thay đổi, tài liệu, tự động hóa, phân tích và xuất dữ liệu.
- Giao diện `/app` dùng React/TypeScript/Vite, Tailwind 4, shadcn/ui, Lucide; backend vẫn là Python. Trang SEO public tiếp tục là HTML tĩnh được server render metadata.
- 5.3 nhóm lại điều hướng, bổ sung liên kết bỏ qua điều hướng và lối vào Thông báo; làm rõ bộ lọc đang áp dụng, kiểm tra khoảng ngày trước khi tra cứu; hiển thị tên gói/trạng thái/theo dõi ở đầu trang chi tiết và thêm thao tác tải lại.
- Điểm tương tác trên biểu đồ xu hướng hỗ trợ bàn phím; màu biểu đồ dùng token sáng/tối. Route quản trị mở trực tiếp dưới `/admin/*` được phục vụ SPA sau khi kiểm tra quyền.

## Kiểm tra và giới hạn

- Local release checks, browser smoke và benchmark được ghi kết quả thực trong [FINAL_RELEASE_5_3.md](FINAL_RELEASE_5_3.md).
- Chưa có kết quả Docker build hoặc kiểm tra Cloud Run/PostgreSQL/GCS thật vì môi trường hiện tại không có Docker, gcloud hay production credentials.
- Truy vấn nguồn e-GP và AI phụ thuộc dịch vụ bên ngoài; benchmark local không đo các dịch vụ đó. PDF scan chưa được cam kết OCR đầy đủ.
- Search job vẫn giữ trạng thái tạm trong RAM instance; cấu hình Cloud Run hiện giới hạn một instance để poll nhất quán. CSS bố cục legacy còn được dùng ở một số khối React, đã kiểm tra hai theme và các viewport mục tiêu.

Triển khai production theo [DEPLOYMENT.md](DEPLOYMENT.md); chỉ mở traffic sau khi các mục còn thiếu trong [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) đạt.
