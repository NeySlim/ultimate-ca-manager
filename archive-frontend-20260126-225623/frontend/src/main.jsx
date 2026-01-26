import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { ThemeProvider } from './contexts/ThemeContext';
import { queryClient } from './lib/queryClient';
import { initTheme } from './theme/theme';
import App from './App.jsx';

// Import animations
import './core/theme/animations.css';
// Import Theme System (12 configurations: 2 themes × 6 accents)
// Note: variables.css is deprecated, using core/theme/global.css instead
// import './theme/variables.css';
import './core/theme/global.css';

// Initialize theme system on app load
initTheme();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <Toaster 
          position="top-right"
          toastOptions={{
            style: {
              background: 'var(--bg-secondary)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius)',
            },
          }}
        />
        <App />
      </ThemeProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);


