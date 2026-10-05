import { afterEach, expect, it, vi } from 'vitest';
import { downloadGet, request, setDownloadDirectory } from './client';

afterEach(() => { setDownloadDirectory(null); vi.unstubAllGlobals(); });
it('uses same-origin API and preserves request ID on error', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: 'Thử lại' }),
    { status: 429, headers: { 'X-Request-ID': 'req-42' } }));
  vi.stubGlobal('fetch', fetcher);
  await expect(request('/api/search')).rejects.toMatchObject(
    { message: 'Thử lại', status: 429, requestId: 'req-42' });
  expect(fetcher).toHaveBeenCalledWith('/api/search', expect.objectContaining({ credentials: 'same-origin' }));
});

it('writes a download to the selected folder with a safe filename', async () => {
  const write = vi.fn().mockResolvedValue(undefined), close = vi.fn().mockResolvedValue(undefined);
  const getFileHandle = vi.fn().mockResolvedValue({ createWritable: async () => ({ write, close }) });
  setDownloadDirectory({ name: 'Reports', getFileHandle } as unknown as FileSystemDirectoryHandle);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('excel bytes',
    { status: 200, headers: { 'X-Filename': 'bad/name.xlsx' } })));
  await downloadGet('/api/download-file?id=abc', 'fallback.xlsx');
  expect(getFileHandle).toHaveBeenCalledWith('bad_name.xlsx', { create: true });
  expect(write).toHaveBeenCalledOnce();
  expect(close).toHaveBeenCalledOnce();
});

it('uses a Unicode Content-Disposition filename when X-Filename is absent', async () => {
  const getFileHandle = vi.fn().mockResolvedValue({ createWritable: async () => ({ write: async () => {}, close: async () => {} }) });
  setDownloadDirectory({ name: 'Reports', getFileHandle } as unknown as FileSystemDirectoryHandle);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('excel bytes',
    { status: 200, headers: { 'Content-Disposition': "attachment; filename*=UTF-8''B%C3%A1o_c%C3%A1o.xlsx" } })));
  await downloadGet('/api/download-file?id=abc', 'fallback.xlsx');
  expect(getFileHandle).toHaveBeenCalledWith('Báo_cáo.xlsx', { create: true });
});
