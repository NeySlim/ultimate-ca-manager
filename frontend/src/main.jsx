import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { AppThemeProvider } from './core/theme/ThemeProvider';
import { ViewProvider } from './core/context/ViewContext';
import { AuthProvider } from './core/context/AuthContext';
import { SelectionProvider } from './core/context/SelectionContext';
import { Toaster } from './components/ui/notifications';
import App from './App.jsx';

// Import Global Styles (NO MORE MANTINE!)
import './core/theme/global.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppThemeProvider>
        <AuthProvider>
          <ViewProvider>
            <SelectionProvider>
              <Toaster position="top-right" />
              <App />
            </SelectionProvider>
          </ViewProvider>
        </AuthProvider>
      </AppThemeProvider>
    </BrowserRouter>
  </React.StrictMode>,
);

