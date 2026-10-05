# Frontend 5.2: hệ thống giao diện

Ứng dụng vẫn dùng React 19, TypeScript 6, Vite 8, Tailwind CSS 4 và Python API hiện có. Cấu hình shadcn/ui nằm trong `frontend/components.json`; `@/` trỏ tới `frontend/src/`. Source của các component được lưu trong `frontend/src/components/ui/`, không sửa `node_modules`.

## Quy ước

- Màu, nền, viền, trạng thái và bo góc dùng semantic tokens trong `src/styles.css`. Theme dùng class `.dark`, đồng bộ với `data-theme` của CSS cũ trong thời gian chuyển tiếp.
- Chỉ dùng Lucide React cho icon mới. Animation từ `tw-animate-css`; tôn trọng `prefers-reduced-motion`.
- Button, Input, Label, Card, Badge, Checkbox, Table, Skeleton, Tooltip, Tabs, DropdownMenu, Dialog, AlertDialog, Sheet, Select, NativeSelect, Switch, Textarea, Command và Sonner lấy từ shadcn/ui. NativeSelect giữ hành vi bàn phím và hiệu năng của `<select>` khi biểu mẫu có nhiều bộ lọc. Không sửa logic request hay URL state để đổi style.
- `src/legacy-bridge.css` giữ bố cục/card/list cũ hoạt động; `src/legacy-tokens.css` dùng cùng semantic tokens cho các phần đó. Selector cũ không áp lên component có `data-slot`.

## Mapping và phạm vi đã áp dụng

| Trước | 5.2 | Đã dùng ở |
| --- | --- | --- |
| Header/sidebar tự viết | Button, Tooltip, Sheet trên di động | Shell |
| Palette tự viết | CommandDialog | Ctrl+K |
| Form đăng nhập/cài đặt | Card, Input, Label, Button, Tabs, Switch | Auth, Settings |
| Bảng tra cứu | Table, Checkbox, DropdownMenu, Badge, Pagination | Tra cứu trực tiếp, Kho dữ liệu |
| Form + xác nhận theo dõi | Card, Select, Textarea, AlertDialog, Sonner | Theo dõi |
| Danh sách trống/đang tải | EmptyState, Skeleton | Tra cứu, Theo dõi, Thông báo, Tải xuống, Lịch sử |
| Prompt bộ lọc/lịch sử | Dialog | Tra cứu, Kho dữ liệu, Lịch sử |
| Bảng thay đổi | Table | Chi tiết gói |
| Thẻ chỉ số và thao tác chính | Card, Skeleton, Button | Tổng quan |
| Button/input/table/textarea/checkbox/select rời rạc | Component shadcn tương ứng | Tất cả React pages |
| `window.confirm` | ConfirmProvider + AlertDialog | Admin, Automation, Analytics, Quality, Report Builder |

`frontend/src/components/data-table/Pagination.tsx` là phân trang dùng chung. Các bảng hiện còn dùng API phù hợp từng nguồn dữ liệu; không đưa logic backend vào component bảng.

## Giới hạn còn lại

Các bố cục chuyên biệt (`.card`, `.form-grid`, `.item-list`, biểu đồ SVG, bảng cuộn) vẫn dùng CSS bridge. Chúng đã nhận màu và trạng thái sáng/tối từ semantic tokens. Gỡ bridge hoàn toàn là công việc polish 5.3 vì sẽ đòi thay bố cục của nhiều luồng nghiệp vụ; không có button/input/select/table native trực tiếp trong React pages, không còn `prompt/confirm`. Các biểu đồ SVG và chi tiết tài liệu giữ nguyên luồng dữ liệu.

Kiểm tra: `npm --prefix frontend run build`, `npm --prefix frontend test`, `npm --prefix frontend run lint`, `tools/smoke_react_browser.cjs` và `tools/predeploy_check.py`. Browser smoke kiểm tra 15 tuyến, 390/1366/1440/1920px, asset 404, JavaScript exception, màu chữ nút chính, đăng nhập, Ctrl+K, lưu bộ lọc, checkbox, Theo dõi, xác nhận xóa, tự động hóa, báo cáo, tải tài liệu và quyền admin.
