import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// The API is same-origin from the app's point of view: it always calls
// relative `/api/...` paths, and in dev this proxy points them at the FastAPI
// process. That keeps the origin out of the client code, so there is no base
// URL to get wrong per environment, and nothing depends on the backend's
// permissive CORS during development.
const API_TARGET = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
})
