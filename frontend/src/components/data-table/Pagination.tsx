import { Button } from '@/components/ui/button';

export function Pagination({ page, total, pageSize, onChange }: { page: number; total: number; pageSize: number; onChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return <nav className="pager" aria-label="Phân trang"><span className="text-sm text-muted-foreground">{total.toLocaleString('vi-VN')} kết quả · Trang {page} / {pages}</span>
    <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>Trước</Button>
    <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>Sau</Button>
  </nav>;
}
