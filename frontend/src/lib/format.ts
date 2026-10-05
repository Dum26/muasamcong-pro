export function dateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat('vi-VN',
    { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(parsed);
}
export function number(value: number | null | undefined): string { return (value ?? 0).toLocaleString('vi-VN'); }
export function tenderCode(row: Tender): string { return row.notify_no || ('PL' + (row.plan_no || row.plan_reference).replace(/^PL/i, '')); }
export function deadlineText(seconds: number | null): string {
  if (seconds === null) return 'Chưa rõ thời gian';
  if (seconds <= 0) return 'Đã đến hạn';
  return `Còn ${Math.floor(seconds / 86400)} ngày ${Math.floor(seconds % 86400 / 3600)} giờ`;
}
import type { Tender } from '../types';
