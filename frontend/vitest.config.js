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
    // The icon barrel is ~4,500 modules: unbundled, each test file spent
    // about 2.5 s importing it, inside the 5 s timeout of the first test that
    // did. Pre-bundled it loads in about 0.1 s.
    deps: {
      optimizer: {
        client: { enabled: true, include: ['@phosphor-icons/react'] },
      },
    },
    pool: 'forks',
    maxForks: 2,
    minForks: 1,
    forks: {
      execArgv: ['--max-old-space-size=4096'],
    },
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
