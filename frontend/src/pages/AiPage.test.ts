import { describe, expect, it } from 'vitest';
import { citationTarget } from './AiPage';

describe('AI citation navigation', () => {
  it('opens the correct comparison document and content page', () => {
    expect(citationTarget('B:S81', 'first', 'second')).toEqual({ documentId: 'second', source: 'S81', page: 2 });
    expect(citationTarget('A:S1', 'first', 'second')).toEqual({ documentId: 'first', source: 'S1', page: 1 });
  });
});
