import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify('test'),
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    exclude: ['node_modules/', 'e2e/**', '**/*.e2e.js', '**/*.spec.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/test/',
        'e2e/',
        '**/*.d.ts',
        'src/main.jsx',
        'src/App.jsx',
        'src/pages/**',  // Pages are integration-tested via E2E
        'src/hooks/**',  // Hooks tested via component tests
        'src/contexts/**'  // Contexts tested via component tests
      ],
      thresholds: {
        // Progressive thresholds - increase as coverage improves
        lines: 50,
        functions: 50,
        branches: 50,
        statements: 50
      }
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  }
})
