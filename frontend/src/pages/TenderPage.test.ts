import { describe, expect, it } from 'vitest';
import { previewDetail } from './TenderPage';
import type { Tender } from '../types';

describe('quick tender preview', () => {
  it('keeps the source row when a live search result has not been synced yet', () => {
    const row = { notify_no: 'IB2600123456', package_name: 'Gói thiết bị', investor_name: 'Bệnh viện A',
      bid_close_date: '30/09/2026 09:00', winner: '', source_url: 'https://muasamcong.mpi.gov.vn/' } as Tender;
    const result = previewDetail(row);
    expect(result.tender.tender_code).toBe('IB2600123456');
    expect(result.tender.investor_name).toBe('Bệnh viện A');
    expect(result.tender.bid_closing_date).toBe('30/09/2026 09:00');
    expect(result.tender.data_health).toBe('Xem nhanh từ kết quả tra cứu');
  });
});
