import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useEffect, useState, type FormEvent } from 'react';
import { useConfirm } from '@/components/shared/ConfirmProvider';
import { Link } from 'react-router';
import { post, request } from '../api/client';
import { dateTime } from '../lib/format';

type Value = string | boolean | [string, string];
interface Condition { field: string; operator: string; value: Value }
interface Group { logic: 'AND' | 'OR'; items: Condition[] }
interface Action { type: string; value: string }
interface Draft { name: string; description: string; trigger_type: string; run_frequency: string; priority: string; is_enabled: boolean; root_logic: 'AND' | 'OR'; groups: Group[]; actions: Action[] }
interface Rule { id: string; name: string; description: string; trigger_type: string; run_frequency: string; priority: string; is_enabled: boolean; conditions_json: { logic: 'AND' | 'OR'; items: Array<Group | Condition> }; actions_json: Action[]; last_run_at: string | null; last_run_error: string | null; next_run_at: string | null }
interface Schema { triggers: Record<string, string>; frequencies: string[]; actions: string[]; fields: Record<'text' | 'number' | 'date' | 'boolean', string[]> }
interface Preview { matched_count: number; scanned_count: number; truncated: boolean; items: Array<{ tender_code: string; title: string }> }
interface Run { id: string; automation_id: string; started_at: string; status: string; matched_count: number; action_count: number; error_message: string | null }
interface AutomationAnalytics { trend: Array<{ day: string; runs: number; matches: number }>; actions: Array<{ action: string; count: number }> }

const ops: Record<keyof Schema['fields'], Array<[string, string]>> = {
  text: [['equals', 'Bằng'], ['not_equals', 'Khác'], ['contains', 'Chứa'], ['not_contains', 'Không chứa'], ['starts_with', 'Bắt đầu'], ['ends_with', 'Kết thúc']],
  number: [['equal', 'Bằng'], ['greater_than', 'Lớn hơn'], ['less_than', 'Nhỏ hơn'], ['between', 'Trong khoảng']],
  date: [['equals', 'Đúng ngày'], ['before', 'Trước'], ['after', 'Sau'], ['within_days', 'Trong N ngày'], ['between', 'Trong khoảng']],
  boolean: [['is', 'Là'], ['is_not', 'Không là']],
};
const actionNames: Record<string, string> = {
  FOLLOW_TENDER: 'Theo dõi gói', UNFOLLOW_TENDER: 'Bỏ theo dõi', ADD_TAG: 'Thêm tag', REMOVE_TAG: 'Xóa tag',
  SET_PRIORITY: 'Đặt ưu tiên', SET_INTERNAL_STATUS: 'Đặt trạng thái', CREATE_NOTIFICATION: 'Tạo thông báo',
  ADD_NOTE_TEMPLATE: 'Thêm ghi chú', QUEUE_DOCUMENT_CHECK: 'Kiểm tra tài liệu',
};
const needsValue = new Set(['ADD_TAG', 'REMOVE_TAG', 'SET_PRIORITY', 'SET_INTERNAL_STATUS', 'ADD_NOTE_TEMPLATE']);
const blank = (): Draft => ({ name: '', description: '', trigger_type: 'NEW_TENDER', run_frequency: 'manual',
  priority: 'normal', is_enabled: false, root_logic: 'AND', groups: [{ logic: 'AND', items: [] }],
  actions: [{ type: 'CREATE_NOTIFICATION', value: '' }] });
function fromRule(rule: Rule): Draft {
  const nested = rule.conditions_json.items.some(item => 'items' in item);
  return { name: rule.name, description: rule.description || '', trigger_type: rule.trigger_type,
    run_frequency: rule.run_frequency, priority: rule.priority, is_enabled: rule.is_enabled,
    root_logic: rule.conditions_json.logic,
    groups: nested ? rule.conditions_json.items.filter((item): item is Group => 'items' in item) :
      [{ logic: rule.conditions_json.logic, items: rule.conditions_json.items as Condition[] }],
    actions: rule.actions_json };
}
export function automationPayload(draft: Draft) {
  return { name: draft.name, description: draft.description, trigger_type: draft.trigger_type,
    run_frequency: draft.run_frequency, priority: draft.priority, is_enabled: draft.is_enabled,
    conditions: draft.groups.length === 1 ? draft.groups[0] : { logic: draft.root_logic, items: draft.groups },
    actions: draft.actions };
}

export function AutomationPage() {
  const confirmAction = useConfirm();
  const [schema, setSchema] = useState<Schema | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [analytics, setAnalytics] = useState<AutomationAnalytics | null>(null);
  const [events, setEvents] = useState<Array<{ entity_id: string; action: string; status: string }> | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editId, setEditId] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  async function load() {
    const [options, list, history, metrics] = await Promise.all([
      request<Schema>('/api/automations/schema'),
      request<{ items: Rule[] }>('/api/automations'),
      request<{ items: Run[] }>('/api/automations/runs'),
      request<AutomationAnalytics>('/api/automations/analytics?days=14'),
    ]);
    setSchema(options); setRules(list.items); setRuns(history.items); setAnalytics(metrics);
  }
  useEffect(() => { void load().catch(caught => setError(String(caught))).finally(() => setLoading(false)); }, []);
  function change(mutator: (next: Draft) => void) { setDraft(current => { if (!current) return current; const next = structuredClone(current); mutator(next); return next; }); setPreview(null); }
  function fieldType(field: string): keyof Schema['fields'] { return (Object.keys(schema?.fields || {}) as Array<keyof Schema['fields']>).find(kind => schema?.fields[kind].includes(field)) || 'text'; }
  function condition(group: number, index: number, patch: Partial<Condition>) {
    change(next => { const old = next.groups[group].items[index]; const kind = fieldType(patch.field || old.field);
      next.groups[group].items[index] = { ...old, ...patch, ...(patch.field ? { operator: ops[kind][0][0], value: kind === 'boolean' ? true : '' } : {}) }; });
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!draft) return;
    setBusy(true); setError('');
    try {
      await post<Rule>(editId ? `/api/automations/${editId}` : '/api/automations', automationPayload(draft));
      setNotice('Đã lưu quy tắc.'); setDraft(null); setEditId(''); setPreview(null); await load();
    } catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }
  async function testDraft() {
    if (!draft) return; setBusy(true); setError('');
    try { setPreview(await post<Preview>('/api/automations/preview', automationPayload(draft))); }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }
  async function ruleAction(rule: Rule, action: 'test' | 'run' | 'enable' | 'pause' | 'duplicate' | 'delete') {
    if (action === 'delete' && !await confirmAction(`Xóa quy tắc ${rule.name}?`)) return;
    setBusy(true); setError(''); setPreview(null);
    try {
      const result = await post<Preview | { matched_count?: number }>(`/api/automations/${rule.id}/${action}`, {});
      if (action === 'test') setPreview(result as Preview);
      else { setNotice(action === 'run' ? `Đã chạy: ${result.matched_count || 0} gói phù hợp.` : 'Đã cập nhật quy tắc.'); await load(); }
    } catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }
  function exportRule(rule: Rule) { const config = { name: rule.name, description: rule.description, trigger_type: rule.trigger_type, conditions: rule.conditions_json, actions: rule.actions_json, run_frequency: rule.run_frequency, priority: rule.priority, is_enabled: false };
    const url = URL.createObjectURL(new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `automation-${rule.id}.json`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }
  async function showEvents(id: string) { setError(''); try { setEvents((await request<{ items: Array<{ entity_id: string; action: string; status: string }> }>(`/api/automations/runs/${id}/events`)).items); } catch (caught) { setError(String(caught)); } }
  const visible = rules.filter(rule => rule.name.toLocaleLowerCase('vi').includes(query.toLocaleLowerCase('vi')));
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">TỰ ĐỘNG HÓA</p><h1>Quy tắc đấu thầu</h1><p>Điều kiện và hành động chạy trên dữ liệu của tài khoản này.</p></div><Button onClick={() => { setDraft(blank()); setEditId(''); setPreview(null); }}>Tạo quy tắc</Button></div>
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}
    {draft && schema && <form className="card automation-editor" onSubmit={event => void save(event)}><h2>{editId ? 'Sửa quy tắc' : 'Quy tắc mới'}</h2><div className="form-grid"><label className="wide">Tên<Input required maxLength={120} value={draft.name} onChange={event => change(next => { next.name = event.target.value; })}/></label><label>Trigger<NativeSelect value={draft.trigger_type} onChange={event => change(next => { next.trigger_type = event.target.value; if (event.target.value === 'MANUAL_RUN') next.run_frequency = 'manual'; })}>{Object.entries(schema.triggers).map(([key, label]) => <NativeSelectOption value={key} key={key}>{label}</NativeSelectOption>)}</NativeSelect></label><label>Tần suất<NativeSelect value={draft.run_frequency} disabled={draft.trigger_type === 'MANUAL_RUN'} onChange={event => change(next => { next.run_frequency = event.target.value; })}>{schema.frequencies.map(value => <NativeSelectOption key={value} value={value}>{value}</NativeSelectOption>)}</NativeSelect></label><label className="wide">Mô tả<Input maxLength={1000} value={draft.description} onChange={event => change(next => { next.description = event.target.value; })}/></label><label>Ưu tiên<NativeSelect value={draft.priority} onChange={event => change(next => { next.priority = event.target.value; })}><NativeSelectOption value="low">Thấp</NativeSelectOption><NativeSelectOption value="normal">Bình thường</NativeSelectOption><NativeSelectOption value="high">Cao</NativeSelectOption></NativeSelect></label><label className="check"><Checkbox checked={draft.is_enabled} onCheckedChange={checked => change(next => { next.is_enabled = checked === true; })}/> Bật sau khi lưu</label></div>
      <h3>Điều kiện</h3>{draft.groups.length > 1 && <label>Kết hợp nhóm<NativeSelect value={draft.root_logic} onChange={event => change(next => { next.root_logic = event.target.value as 'AND' | 'OR'; })}><NativeSelectOption>AND</NativeSelectOption><NativeSelectOption>OR</NativeSelectOption></NativeSelect></label>}{draft.groups.map((group, groupIndex) => <fieldset className="automation-group" key={groupIndex}><legend>Nhóm {groupIndex + 1}</legend><div className="form-actions"><NativeSelect aria-label={`Kết hợp điều kiện nhóm ${groupIndex + 1}`} value={group.logic} onChange={event => change(next => { next.groups[groupIndex].logic = event.target.value as 'AND' | 'OR'; })}><NativeSelectOption>AND</NativeSelectOption><NativeSelectOption>OR</NativeSelectOption></NativeSelect><Button type="button" className="secondary" onClick={() => change(next => { next.groups[groupIndex].items.push({ field: 'title', operator: 'contains', value: '' }); })}>Thêm điều kiện</Button>{draft.groups.length > 1 && <Button type="button" className="secondary" onClick={() => change(next => { next.groups.splice(groupIndex, 1); })}>Bỏ nhóm</Button>}</div>{group.items.map((item, index) => { const kind = fieldType(item.field); return <div className="automation-condition" key={index}><NativeSelect aria-label="Trường" value={item.field} onChange={event => condition(groupIndex, index, { field: event.target.value })}>{Object.entries(schema.fields).flatMap(([, fields]) => fields).map(field => <NativeSelectOption key={field} value={field}>{field}</NativeSelectOption>)}</NativeSelect><NativeSelect aria-label="So sánh" value={item.operator} onChange={event => condition(groupIndex, index, { operator: event.target.value, value: event.target.value === 'between' ? ['', ''] : kind === 'boolean' ? true : '' })}>{ops[kind].map(([value, label]) => <NativeSelectOption key={value} value={value}>{label}</NativeSelectOption>)}</NativeSelect>{kind === 'boolean' ? <NativeSelect aria-label="Giá trị" value={String(item.value)} onChange={event => condition(groupIndex, index, { value: event.target.value === 'true' })}><NativeSelectOption value="true">Có</NativeSelectOption><NativeSelectOption value="false">Không</NativeSelectOption></NativeSelect> : Array.isArray(item.value) ? <><Input aria-label="Từ" type={kind === 'date' ? 'date' : 'number'} value={item.value[0]} onChange={event => condition(groupIndex, index, { value: [event.target.value, (item.value as [string, string])[1]] })}/><Input aria-label="Đến" type={kind === 'date' ? 'date' : 'number'} value={item.value[1]} onChange={event => condition(groupIndex, index, { value: [(item.value as [string, string])[0], event.target.value] })}/></> : <Input aria-label="Giá trị" type={kind === 'date' && item.operator !== 'within_days' ? 'date' : kind === 'number' || item.operator === 'within_days' ? 'number' : 'text'} value={String(item.value)} onChange={event => condition(groupIndex, index, { value: event.target.value })}/>}<Button type="button" className="secondary" onClick={() => change(next => { next.groups[groupIndex].items.splice(index, 1); })}>Bỏ</Button></div>; })}</fieldset>)}<Button type="button" className="secondary" disabled={draft.groups.length >= 3} onClick={() => change(next => { next.groups.push({ logic: 'AND', items: [] }); })}>Thêm nhóm điều kiện</Button>
      <h3>Hành động</h3>{draft.actions.map((item, index) => <div className="automation-condition" key={index}><NativeSelect aria-label="Hành động" value={item.type} onChange={event => change(next => { next.actions[index] = { type: event.target.value, value: '' }; })}>{schema.actions.map(type => <NativeSelectOption value={type} key={type}>{actionNames[type] || type}</NativeSelectOption>)}</NativeSelect>{needsValue.has(item.type) && (item.type === 'SET_PRIORITY' || item.type === 'SET_INTERNAL_STATUS' ? <NativeSelect aria-label="Giá trị hành động" value={item.value} onChange={event => change(next => { next.actions[index].value = event.target.value; })}><NativeSelectOption value="">Chọn</NativeSelectOption>{(item.type === 'SET_PRIORITY' ? ['Thấp', 'Trung bình', 'Cao', 'Khẩn cấp'] : ['Mới', 'Đang xem', 'Quan tâm', 'Đang xử lý', 'Hoàn tất', 'Bỏ qua']).map(value => <NativeSelectOption key={value}>{value}</NativeSelectOption>)}</NativeSelect> : <Input aria-label="Giá trị hành động" value={item.value} onChange={event => change(next => { next.actions[index].value = event.target.value; })}/>)}<Button type="button" className="secondary" disabled={draft.actions.length <= 1} onClick={() => change(next => { next.actions.splice(index, 1); })}>Bỏ</Button></div>)}<div className="form-actions"><Button type="button" className="secondary" disabled={draft.actions.length >= 8} onClick={() => change(next => { next.actions.push({ type: 'CREATE_NOTIFICATION', value: '' }); })}>Thêm hành động</Button><Button type="button" className="secondary" disabled={busy} onClick={() => void testDraft()}>Xem trước · không thực hiện</Button><Button disabled={busy}>Lưu quy tắc</Button><Button type="button" className="secondary" onClick={() => { setDraft(null); setPreview(null); }}>Hủy</Button></div></form>}
    {preview && <section className="card"><h2>Bản xem trước</h2><p>{preview.matched_count}{preview.truncated ? '+' : ''} / {preview.scanned_count} gói phù hợp. Chưa thực hiện hành động.</p>{preview.truncated && <p>Chỉ quét 1.000 ứng viên đầu; hãy thêm điều kiện để thu hẹp.</p>}<div className="item-list">{preview.items.map(item => <Link className="list-item" to={`/app/tenders/${encodeURIComponent(item.tender_code)}`} key={item.tender_code}>{item.tender_code} · {item.title}</Link>)}</div></section>}
    <section className="card"><div className="results-head"><h2>Danh sách quy tắc</h2><Input aria-label="Tìm quy tắc" value={query} onChange={event => setQuery(event.target.value)} placeholder="Tìm theo tên"/></div>{loading ? <div className="skeleton"/> : !visible.length ? <p className="empty">Chưa có quy tắc phù hợp.</p> : <div className="item-list">{visible.map(rule => <article className="list-item" key={rule.id}><span><strong>{rule.name}</strong><small>{schema?.triggers[rule.trigger_type] || rule.trigger_type} · {rule.is_enabled ? 'Đang bật' : 'Tạm dừng'} · Lần chạy cuối: {dateTime(rule.last_run_at)}</small>{rule.last_run_error && <small className="error">{rule.last_run_error}</small>}</span><div className="form-actions"><Button className="secondary" disabled={busy} onClick={() => { setDraft(fromRule(rule)); setEditId(rule.id); setPreview(null); }}>Sửa</Button><Button className="secondary" disabled={busy} onClick={() => void ruleAction(rule, 'test')}>Test</Button><Button className="secondary" disabled={busy} onClick={() => void ruleAction(rule, 'run')}>Chạy ngay</Button><Button className="secondary" disabled={busy} onClick={() => void ruleAction(rule, rule.is_enabled ? 'pause' : 'enable')}>{rule.is_enabled ? 'Tạm dừng' : 'Bật'}</Button><Button className="secondary" disabled={busy} onClick={() => void ruleAction(rule, 'duplicate')}>Nhân bản</Button><Button className="secondary" onClick={() => exportRule(rule)}>Xuất JSON</Button><Button className="secondary" disabled={busy} onClick={() => void ruleAction(rule, 'delete')}>Xóa</Button></div></article>)}</div>}</section>
    <section className="card"><h2>Lịch sử chạy gần đây</h2>{runs.length ? <div className="table-scroll"><Table><TableHeader><TableRow><TableHead>Thời gian</TableHead><TableHead>Quy tắc</TableHead><TableHead>Trạng thái</TableHead><TableHead>Gói khớp</TableHead><TableHead>Hành động</TableHead><TableHead>Lỗi</TableHead><TableHead>Chi tiết</TableHead></TableRow></TableHeader><TableBody>{runs.slice(0, 30).map(run => <TableRow key={run.id}><TableCell>{dateTime(run.started_at)}</TableCell><TableCell>{rules.find(rule => rule.id === run.automation_id)?.name || run.automation_id}</TableCell><TableCell>{run.status}</TableCell><TableCell>{run.matched_count}</TableCell><TableCell>{run.action_count}</TableCell><TableCell>{run.error_message || '—'}</TableCell><TableCell><Button className="secondary" onClick={() => void showEvents(run.id)}>Sự kiện</Button></TableCell></TableRow>)}</TableBody></Table></div> : <p className="empty">Chưa có lượt chạy.</p>}{events && <div><h3>Sự kiện của lượt chọn</h3>{events.length ? events.map((event, index) => <p key={index}>{event.entity_id} · {event.action} · {event.status}</p>) : <p>Không có hành động mới.</p>}</div>}</section>
    {analytics && <section className="card"><h2>Hoạt động 14 ngày</h2>{analytics.trend?.length ? <div className="bar-list">{analytics.trend.map(item => <div key={item.day}><span>{item.day}</span><div><i style={{ width: `${Math.max(2, item.runs / Math.max(1, ...analytics.trend.map(point => point.runs)) * 100)}%` }}/></div><b>{item.runs}</b></div>)}</div> : <p>Chưa có lượt chạy.</p>}</section>}
  </main>;
}
