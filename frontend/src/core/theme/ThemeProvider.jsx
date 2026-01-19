import React, { createContext, useContext, useState, useEffect } from 'react';
import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import { createAppTheme } from './mantine.config';
import { defaultPalette } from './colors';

const ThemeContext = createContext();

export const useAppTheme = () => useContext(ThemeContext);

export const AppThemeProvider = ({ children }) => {
  const [activePalette, setActivePalette] = useState(() => {
    return localStorage.getItem('ucm-palette') || defaultPalette;
  });

  const [theme, setTheme] = useState(createAppTheme(activePalette));

  useEffect(() => {
    setTheme(createAppTheme(activePalette));
    localStorage.setItem('ucm-palette', activePalette);
  }, [activePalette]);

  const value = {
    activePalette,
    setActivePalette,
  };

  return (
    <ThemeContext.Provider value={value}>
      <MantineProvider theme={theme} defaultColorScheme="dark">
        <ModalsProvider>
          {children}
        </ModalsProvider>
      </MantineProvider>
    </ThemeContext.Provider>
  );
};
