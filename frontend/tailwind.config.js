/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  safelist: [
    'grid-cols-1', 'grid-cols-2', 'grid-cols-3', 'grid-cols-4',
    'lg:grid-cols-1', 'lg:grid-cols-2', 'lg:grid-cols-3', 'lg:grid-cols-4',
    'xl:grid-cols-1', 'xl:grid-cols-2', 'xl:grid-cols-3', 'xl:grid-cols-4',
    'lg:gap-4', 'lg:gap-6', 'lg:p-6', 'lg:space-y-6',
  ],
  theme: {
    extend: {
      colors: {
        // Background colors
        'bg-primary': 'var(--bg-primary)',
        'bg-secondary': 'var(--bg-secondary)',
        'bg-tertiary': 'var(--bg-tertiary)',
        'bg-hover': 'var(--bg-tertiary)',
        
        // Text colors  
        'text-primary': 'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'text-tertiary': 'var(--text-tertiary)',
        
        // Accent colors with RGB for opacity support
        'accent-primary': 'var(--accent-primary)',
        'accent-pro': 'var(--accent-pro)',
        
        // Status colors - these map to theme variables
        'status-success': 'var(--accent-success)',
        'status-warning': 'var(--accent-warning)', 
        'status-danger': 'var(--accent-danger)',
        'status-error': 'var(--accent-danger)',
        'status-info': 'var(--accent-primary)',
        
        // Legacy mappings (for compatibility)
        'accent-success': 'var(--accent-success)',
        'accent-warning': 'var(--accent-warning)',
        'accent-danger': 'var(--accent-danger)',
        
        // Border
        'border': 'var(--border)',
        'border-hover': 'var(--text-tertiary)',
      },
      fontFamily: {
        sans: ['Geist', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
        mono: ['SF Mono', 'Monaco', 'Cascadia Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'slide-in-right': 'slideInRight 0.2s ease-out',
        'slide-up': 'slideUp 0.25s ease-out',
        'fade-in': 'fadeIn 0.15s ease-out',
      },
      keyframes: {
        slideInRight: {
          '0%': { transform: 'translateX(100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(100%)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
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
