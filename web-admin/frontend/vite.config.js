import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 18701,
    host: '127.0.0.1',
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18700',
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 18701,
    host: '127.0.0.1',
    strictPort: true,
  },
});
