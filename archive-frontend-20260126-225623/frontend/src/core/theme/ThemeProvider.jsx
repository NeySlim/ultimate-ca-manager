import React from 'react';
import { ThemeProvider as StateThemeProvider } from '../../contexts/ThemeContext';

/**
 * Simplified ThemeProvider - NO MORE MANTINE!
 * Just wraps StateThemeProvider (ThemeContext)
 */
export const AppThemeProvider = ({ children }) => {
  return (
    <StateThemeProvider>
      {children}
    </StateThemeProvider>
  );
};
