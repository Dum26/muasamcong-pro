import { describe, expect, it } from 'vitest';
import { deadlineText, tenderCode } from './format';
import type { Tender } from '../types';

describe('tender presentation', () => {
  it('keeps official TBMT code and formats KHLCNT without a suffix', () => {
    expect(tenderCode({ notify_no: 'IB2600123456' } as Tender)).toBe('IB2600123456');
    expect(tenderCode({ notify_no: '', plan_no: 'PL2600320489' } as Tender)).toBe('PL2600320489');
  });
  it('shows remaining time without guessing unknown deadlines', () => {
    expect(deadlineText(null)).toBe('Chưa rõ thời gian');
    expect(deadlineText(90000)).toBe('Còn 1 ngày 1 giờ');
  });
});
