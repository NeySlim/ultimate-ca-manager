/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'bg-primary': 'var(--bg-primary)',
        'bg-secondary': 'var(--bg-secondary)',
        'bg-tertiary': 'var(--bg-tertiary)',
        'text-primary': 'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'accent-primary': 'var(--accent-primary)',
        'accent-success': 'var(--accent-success)',
        'accent-warning': 'var(--accent-warning)',
        'accent-danger': 'var(--accent-danger)',
        'border': 'var(--border)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['SF Mono', 'Monaco', 'Cascadia Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      borderRadius: {
        'sm': '0.125rem',  // 2px
        'DEFAULT': '0.25rem', // 4px
        'md': '0.25rem',   // 4px
        'lg': '0.375rem',  // 6px
        'xl': '0.5rem',    // 8px
      },
      spacing: {
        '0.5': '0.125rem',
        '1': '0.25rem',
        '1.5': '0.375rem',
        '2': '0.5rem',
        '2.5': '0.625rem',
        '3': '0.75rem',
        '3.5': '0.875rem',
        '4': '1rem',
      },
    },
  },
  plugins: [],
}
