export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly requestId: string | null) { super(message); }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (!path.startsWith('/api/')) throw new Error('API path phải là relative /api/.');
  const response = await fetch(path, { credentials: 'same-origin', ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event('msc:session-expired'));
    const body: unknown = await response.json().catch(() => null);
    const message = typeof body === 'object' && body !== null && 'error' in body && typeof body.error === 'string'
      ? body.error : `Không lấy được dữ liệu (HTTP ${response.status}).`;
    throw new ApiError(message, response.status, response.headers.get('X-Request-ID'));
  }
  return response.json() as Promise<T>;
}

export function post<T>(path: string, body: object): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}

let directory: FileSystemDirectoryHandle | null = null;
export function setDownloadDirectory(value: FileSystemDirectoryHandle | null) { directory = value; }
export function downloadDirectoryName() { return directory?.name || null; }

async function saveResponse(response: Response, fallback: string) {
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event('msc:session-expired'));
    const data: unknown = await response.json().catch(() => null);
    throw new ApiError(typeof data === 'object' && data !== null && 'error' in data && typeof data.error === 'string'
      ? data.error : 'Không tải được file.', response.status, response.headers.get('X-Request-ID'));
  }
  const disposition = response.headers.get('Content-Disposition') || '';
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const quoted = disposition.match(/filename="([^"]+)"/i)?.[1];
  let headerName = quoted || '';
  if (encoded) { try { headerName = decodeURIComponent(encoded); } catch { /* Invalid server filename; use fallback. */ } }
  const filename = (response.headers.get('X-Filename') || headerName || fallback).replace(/[\\/:*?"<>|\x00-\x1f]/g, '_').slice(0, 180);
  const blob = await response.blob();
  if (directory) {
    const file = await directory.getFileHandle(filename, { create: true });
    const writer = await file.createWritable();
    try { await writer.write(blob); await writer.close(); }
    catch (error) { await writer.abort(); throw error; }
    return;
  }
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export async function download(path: string, body: object, fallback: string): Promise<void> {
  if (!path.startsWith('/api/')) throw new Error('API path phải là relative /api/.');
  const response = await fetch(path, { method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  await saveResponse(response, fallback);
}

export async function downloadGet(path: string, fallback: string): Promise<void> {
  if (!path.startsWith('/api/')) throw new Error('API path phải là relative /api/.');
  await saveResponse(await fetch(path, { credentials: 'same-origin' }), fallback);
}
