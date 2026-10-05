export interface User { id: string; email: string; role: 'admin' | 'user'; created_at: string; last_login_at: string | null }
export interface Tender {
  index: number; notify_no: string; plan_no: string; plan_reference: string;
  package_name: string; plan_name: string; investor_name: string;
  procuring_entity_name: string; package_price: string; public_date: string;
  bid_close_date: string; tender_status: string; location: string;
  bid_form: string; winner: string; winning_price: string;
  source_url: string; lot_file_status: string; has_lots: boolean;
}
export interface CanonicalTender {
  tender_code: string; khlcnt_code: string | null; title: string;
  investor_name: string | null; procuring_entity_name: string | null;
  package_price: string | null; winning_price: string | null;
  publish_date: string | null; bid_closing_date: string | null;
  status: string | null; selection_method: string | null; location: string | null;
  winning_contractor: string | null; source_url: string | null;
  data_health: string; last_synced_at: string | null;
}
export interface TenderDetailResponse { tender: CanonicalTender; timeline: Array<{ event_type: string; event_at: string; description?: string }>; changes: Array<{ field_name: string; old_value: string; new_value: string; detected_at: string }>; documents: Array<{ id: string; filename: string; status: string }>; related: Array<{ tender_code: string; title: string; reason: string }> }
export interface PlanDetailResponse { plan: { plan_code: string; title: string; investor_name: string | null; publish_date: string | null }; package_count: number; packages: Array<{ tender_code: string; title: string }> }
export interface SearchParams {
  mode: 'Thông báo mời thầu' | 'Kế hoạch lựa chọn nhà thầu';
  keyword: string; use_dates: boolean; date_from: string; date_to: string;
  status: string; pages: number; detail: boolean; fast_mode: boolean;
  remove_duplicates: boolean; bid_form: string; location: string;
}
export interface SearchJob { id: string; state: 'queued' | 'running' | 'done' | 'error'; message: string; error: string; count: number; source_count: number; fetched_at: string; rows?: Tender[] }
export interface WatchItem { code: string; name: string; investor: string; deadline: string; status: string; priority: string; workflow_status: string; note: string; tags: string[]; pinned: boolean; has_update: boolean; snapshot: Partial<Tender>; changes: Array<{ field: string; before: string; after: string }> }
export interface SavedSearch { id: string; name: string; params: SearchParams; pinned: boolean; is_watch_enabled: boolean; last_run_at: string | null }
export type HistoryItem = Partial<Omit<SearchParams, 'mode'>> & {
  id: string; name?: string; mode?: SearchParams['mode'] | 'Kho dữ liệu';
  time?: string; created_at?: string; result_count?: number; pinned?: boolean;
};
export interface Notification { id: string; title: string; message: string; tender_code: string | null; is_read: boolean; created_at: string }
export interface DownloadItem { id: string; name: string; kind: string; status: string; size: number | null; error: string; time: string; url: string }
export interface Analytics { total_tenders: number; dated_tenders: number; missing_dates: number; series: Array<{ period: string; tenders: number }>; top_investors: Array<{ investor_name: string; count: number }> }
export interface Deadline { tender_code: string; title: string; investor_name: string; bid_closing_date: string; remaining_seconds: number | null }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
