import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': new URL('./src', import.meta.url).pathname.replace(/^\/(\w):/, '$1:') } },
  base: '/',
  server: { proxy: { '/api': 'http://127.0.0.1:54939' } },
  test: { environment: 'node' },
});
