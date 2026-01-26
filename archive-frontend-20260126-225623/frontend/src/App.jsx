import React from 'react';
import { BrowserRouter } from 'react-router';
import { AppRoutes } from './routes';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './design-system/themes';
import { CommandPalette, useCommandPalette } from './design-system/components/features/CommandPalette';

/**
 * Main App Component with Auth Protection
 */
function App() {
  const { isOpen, close } = useCommandPalette();

  return (
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
          <CommandPalette isOpen={isOpen} onClose={close} />
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
