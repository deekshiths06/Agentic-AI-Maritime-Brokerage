import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
//
// - host: true binds Vite to 0.0.0.0 so the app is reachable from
//   other devices on the same network (e.g. a mobile phone).
// - port stays at 5173.
// - /api is proxied to the FastAPI backend on the same machine, so
//   the frontend never needs a machine-specific backend URL. The
//   target can be overridden with VITE_API_URL (e.g. a LAN IP) without
//   committing that value to the repository.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})