import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import react from 'eslint-plugin-react'

export default [
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**'] },
  // Test files — allow globals (vitest/jest)
  {
    files: ['**/*.test.{js,jsx}', '**/test/**/*.{js,jsx}', '**/__tests__/**/*.{js,jsx}'],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.es2021,
        ...globals.node,
        global: 'writable',
        vi: 'readonly',
        describe: 'readonly',
        it: 'readonly',
        expect: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
      },
    },
  },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: {
        ...globals.browser,
        ...globals.es2021,
        __APP_VERSION__: 'readonly',
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      // React hooks — catches stale closures & missing deps
      ...reactHooks.configs.recommended.rules,

      // React 19 strict rules — disable (only in react-hooks v7+)
      // 'react-hooks/set-state-in-effect': 'off',
      // 'react-hooks/refs': 'off',
      // 'react-hooks/purity': 'off',
      // 'react-hooks/immutability': 'off',

      // React refresh — warns on non-component exports
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // React JSX runtime (no need to import React)
      'react/react-in-jsx-scope': 'off',
      'react/jsx-uses-react': 'off',
      'react/jsx-uses-vars': 'error',

      // Catch real bugs
      'no-undef': 'error',
      'no-unused-vars': ['warn', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        destructuredArrayIgnorePattern: '^_',
      }],
      'no-constant-condition': 'warn',
      'no-debugger': 'error',
      'no-duplicate-case': 'error',
      'no-empty': ['warn', { allowEmptyCatch: true }],
      'no-unreachable': 'error',
      'eqeqeq': ['warn', 'smart'],

      // Off — too noisy for existing codebase
      'react/prop-types': 'off',
      'react/display-name': 'off',
      'no-prototype-builtins': 'off',
    },
    settings: {
      react: { version: 'detect' },
    },
  },
]
