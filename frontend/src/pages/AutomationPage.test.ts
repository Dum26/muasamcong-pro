import { describe, expect, it } from 'vitest';
import { automationPayload } from './AutomationPage';

describe('automation builder', () => {
  it('sends nested AND/OR groups in the Python API shape', () => {
    const result = automationPayload({ name: 'Test', description: '', trigger_type: 'NEW_TENDER',
      run_frequency: 'manual', priority: 'normal', is_enabled: false, root_logic: 'OR',
      groups: [
        { logic: 'AND', items: [{ field: 'title', operator: 'contains', value: 'thuốc' }] },
        { logic: 'AND', items: [{ field: 'investor_name', operator: 'contains', value: 'bệnh viện' }] },
      ], actions: [{ type: 'CREATE_NOTIFICATION', value: '' }] });
    expect(result.conditions).toMatchObject({ logic: 'OR', items: [{ logic: 'AND' }, { logic: 'AND' }] });
  });
});
