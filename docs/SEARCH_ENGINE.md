# Search Engine 2.0 — trạng thái triển khai

`server/search_engine.py` tìm trên kho dữ liệu công khai đã đồng bộ: TBMT, KHLCNT, chủ đầu tư, bên mời thầu và nhà thầu. Tra cứu live e-GP (`POST /api/search`) vẫn hoạt động như trước; nút **Tìm trong dữ liệu đã đồng bộ** không gọi nguồn ngoài. Ctrl+K dùng cùng dịch vụ qua endpoint gợi ý.

## API

- `GET /api/intelligence/search?q=...&page=1&page_size=25` trả `items`, `page`, `page_size`, `total`, `total_pages`.
- `GET /api/intelligence/suggest?q=...` trả tối đa 10 kết quả.
- Cả hai endpoint yêu cầu đăng nhập. `sort` chỉ nhận `relevance`, `published`, `deadline`, `price`, `name`, `updated`; `order` chỉ nhận `asc`/`desc`.
- Bộ lọc trên TBMT: `status`, `location`, `investor`, `procurer`, `contractor`, `from`, `to`, `deadline_from`, `deadline_to`, `price_min`, `price_max`, `selection_method`, `contract_type`, `results=1`. Khi có bộ lọc riêng của TBMT, chỉ trả TBMT.
- Ô query cũng nhận `investor:`, `contractor:`, `procurer:`, `status:`, `before:YYYY-MM-DD`, `after:YYYY-MM-DD` và `price:>500000000`. Cú pháp không hợp lệ được xem như từ khóa thường; filter UI/API tường minh có ưu tiên cao hơn operator.
- `GET /api/intelligence/admin/search-metrics?days=14` chỉ dành cho admin, trả số lượt tìm, thời gian trung bình, tỷ lệ không có kết quả, tỷ lệ cache hit và số liệu theo ngày/loại. Không lưu nội dung query.
- GET tìm trong kho giới hạn 60 lượt/phút/tài khoản; gợi ý giới hạn 180 lượt/phút/tài khoản. Giới hạn này hiện theo từng tiến trình, phù hợp local; khi cần giới hạn toàn cụm Cloud Run phải chuyển bộ đếm sang kho dùng chung.

Migration v11 thêm `search_text` chuẩn hóa không dấu cho bản ghi hiện có, và luồng ingest duy trì trường này cho bản ghi mới. Migration v12 thêm số liệu tìm kiếm tổng hợp theo ngày/loại. Migration v13 tạo GIN full-text index trên PostgreSQL cho năm bảng tìm kiếm; SQLite giữ fallback `LIKE`. Dữ liệu gốc không bị sửa. Ranking: mã chính xác, tên chính xác, mã bắt đầu bằng query, tên bắt đầu bằng query, full-text, chuỗi chuẩn hóa, rồi fuzzy. Khi không có kết quả, truy vấn dài có thể thử fuzzy giới hạn trong tối đa 300 ứng viên có cùng từ đầu; mức tương đồng tối thiểu 0,78. Kết quả fuzzy đánh dấu `rank=6`.

Kết quả DB được cache tối đa 15 giây trong mỗi tiến trình, tối đa 128 khóa. Các request cùng khóa trong một tiến trình dùng chung phép tính; ingest làm rỗng cache, `refresh=1` bỏ qua cache. Cache không chia sẻ giữa nhiều Cloud Run instance và không chứa thông tin riêng từng tài khoản.

Trang `/app/search?q=...` giữ query, filter, loại dữ liệu, sort, số dòng và trang trong URL. Bảng kết quả chỉ hiển thị một trang; link mã mở chi tiết, nút sao chép mã và theo dõi TBMT/KHLCNT. Ctrl+K debounce 200 ms, dùng `AbortController` để bỏ phản hồi cũ. HTML kết quả được dựng bằng DOM/textContent, từ khóa được tô sáng bằng node `mark` thay vì ghép HTML.

Lịch sử chỉ ghi khi một truy vấn kho dữ liệu hoàn thành, theo từng tài khoản và kèm số kết quả. Bộ lọc kho dữ liệu dùng chung bảng saved search hiện có, nhưng giao diện tách khỏi preset tìm live để không áp dụng nhầm chế độ. Bộ lọc kho được bật theo dõi có thể chạy qua queue Data Sync; lần đầu tạo baseline, lần sau báo mã TBMT/KHLCNT mới.

## Hiệu năng và giới hạn

Benchmark SQLite local tổng hợp bằng `python -m tools.bench_search 10000` và `50000`; không phải số đo production. Ở máy thử: 10k bản ghi — mã 36,8 ms, text 32,3 ms, lọc giá 8,8 ms; 50k khi chạy riêng — mã 111,3 ms, text 133,8 ms, lọc giá 25,8 ms; 50k khi chạy song song toàn bộ test — mã 315,5 ms, text 418,4 ms, lọc giá 95,4 ms. Các số này phụ thuộc máy, tải CPU, dữ liệu, cache và hệ quản trị. PostgreSQL có GIN full-text index nhưng chưa có kết quả EXPLAIN trên dữ liệu production. Nhánh khớp chuỗi `LIKE '%...%'` vẫn có thể quét bảng; cần đo thực tế rồi cân nhắc `pg_trgm` nếu nó trở thành bottleneck.

Panel trong workspace cho lọc ngày, hạn đóng thầu, trạng thái, địa điểm, chủ đầu tư, bên mời thầu, nhà thầu, hình thức, loại hợp đồng, giá và KQLCNT. Parser của `/api/intelligence/tenders` vẫn hoạt động riêng để giữ tương thích. Bộ lọc theo dõi kho quét mọi trang theo lô nội bộ 1.000 dòng, không bỏ sót phần sau trang 10; các bộ lọc khớp hàng triệu dòng có thể cần checkpoint để tránh job chạy quá lâu. Không giả định dữ liệu chưa từng đồng bộ tồn tại trong kho.
