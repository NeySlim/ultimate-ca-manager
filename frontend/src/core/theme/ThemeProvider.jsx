import React from 'react';
import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import { ThemeProvider as StateThemeProvider, useTheme } from '../../contexts/ThemeContext';
import { createMantineTheme } from '../../theme/mantine.config';

const MantineWrapper = ({ children }) => {
  const { palette, density, colorScheme } = useTheme();
  // Memoize theme creation if needed, but creates object is cheap
  const theme = createMantineTheme(palette, density);

  return (
    <MantineProvider theme={theme} defaultColorScheme={colorScheme} forceColorScheme={colorScheme}>
      <ModalsProvider>
        {children}
      </ModalsProvider>
    </MantineProvider>
  );
};

export const AppThemeProvider = ({ children }) => {
  return (
    <StateThemeProvider>
      <MantineWrapper>
        {children}
      </MantineWrapper>
    </StateThemeProvider>
  );
};
