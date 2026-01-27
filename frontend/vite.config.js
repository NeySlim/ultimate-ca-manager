import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  css: {
    postcss: {
      plugins: [],
    },
    devSourcemap: true,
  },
  build: {
    cssCodeSplit: false,
    minify: 'esbuild',
  }
})
