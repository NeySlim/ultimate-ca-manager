import React from 'react';
import ReactDOM from 'react-dom/client';
import { Toaster } from 'react-hot-toast';
import { ThemeProvider } from './contexts/ThemeContext';
import { initTheme } from './theme/theme';
import App from './App.jsx';

// Import Theme System (12 configurations: 2 themes × 6 accents)
import './theme/variables.css';
import './core/theme/global.css';

// Initialize theme system on app load
initTheme();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
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
  </React.StrictMode>,
);


