import React from 'react';
import { BrowserRouter } from 'react-router';
import { AppRoutes } from './routes';
import { AuthProvider } from './contexts/AuthContext';

/**
 * Main App Component with Auth Protection
 */
function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
