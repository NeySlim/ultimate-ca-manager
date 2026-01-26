import React from 'react';
import { BrowserRouter } from 'react-router';
import { AppRoutes } from './routes';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './design-system/themes';

/**
 * Main App Component with Auth Protection
 */
function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
