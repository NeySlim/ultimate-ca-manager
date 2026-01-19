/**
 * Theme Context Provider
 * Manages palette, color scheme, and density with localStorage persistence
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { MantineProvider, MantineTheme, createTheme, MantineColorsTuple } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { ModalsProvider } from '@mantine/modals';
import { ColorPalette, ColorScheme, DensityLevel, ThemeConfig } from '../types/theme';
import { PALETTES } from '../styles/palettes';
import { DENSITY_CONFIGS } from '../styles/density';

import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import '@mantine/modals/styles.css';

interface ThemeContextValue {
  palette: ColorPalette;
  colorScheme: ColorScheme;
  density: DensityLevel;
  setPalette: (palette: ColorPalette) => void;
  setColorScheme: (scheme: ColorScheme) => void;
  setDensity: (density: DensityLevel) => void;
  toggleColorScheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

const STORAGE_KEYS = {
  PALETTE: 'ucm-palette',
  COLOR_SCHEME: 'ucm-color-scheme',
  DENSITY: 'ucm-density',
};

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [palette, setPaletteState] = useState<ColorPalette>(() => {
    const stored = localStorage.getItem(STORAGE_KEYS.PALETTE);
    return (stored as ColorPalette) || 'teal';
  });

  const [colorScheme, setColorSchemeState] = useState<ColorScheme>(() => {
    const stored = localStorage.getItem(STORAGE_KEYS.COLOR_SCHEME);
    return (stored as ColorScheme) || 'light';
  });

  const [density, setDensityState] = useState<DensityLevel>(() => {
    const stored = localStorage.getItem(STORAGE_KEYS.DENSITY);
    return (stored as DensityLevel) || 'normal';
  });

  const setPalette = (newPalette: ColorPalette) => {
    setPaletteState(newPalette);
    localStorage.setItem(STORAGE_KEYS.PALETTE, newPalette);
  };

  const setColorScheme = (newScheme: ColorScheme) => {
    setColorSchemeState(newScheme);
    localStorage.setItem(STORAGE_KEYS.COLOR_SCHEME, newScheme);
  };

  const setDensity = (newDensity: DensityLevel) => {
    setDensityState(newDensity);
    localStorage.setItem(STORAGE_KEYS.DENSITY, newDensity);
  };

  const toggleColorScheme = () => {
    setColorScheme(colorScheme === 'light' ? 'dark' : 'light');
  };

  // Convert palette to Mantine color tuple
  const paletteColors = PALETTES[palette];
  const primaryColor: MantineColorsTuple = [
    paletteColors[50],
    paletteColors[100],
    paletteColors[200],
    paletteColors[300],
    paletteColors[400],
    paletteColors[500],
    paletteColors[600],
    paletteColors[700],
    paletteColors[800],
    paletteColors[900],
  ];

  const densityConfig = DENSITY_CONFIGS[density];

  const theme = createTheme({
    primaryColor: 'primary',
    colors: {
      primary: primaryColor,
    },
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    fontSizes: {
      xs: `${densityConfig.fontSize.xs}px`,
      sm: `${densityConfig.fontSize.sm}px`,
      md: `${densityConfig.fontSize.md}px`,
      lg: `${densityConfig.fontSize.lg}px`,
      xl: `${densityConfig.fontSize.xl}px`,
    },
    spacing: {
      xs: `${densityConfig.spacing.xs}px`,
      sm: `${densityConfig.spacing.sm}px`,
      md: `${densityConfig.spacing.md}px`,
      lg: `${densityConfig.spacing.lg}px`,
      xl: `${densityConfig.spacing.xl}px`,
    },
    radius: {
      xs: `${densityConfig.radius.xs}px`,
      sm: `${densityConfig.radius.sm}px`,
      md: `${densityConfig.radius.md}px`,
      lg: `${densityConfig.radius.lg}px`,
      xl: `${densityConfig.radius.xl}px`,
    },
    defaultRadius: 'md',
    components: {
      Input: {
        styles: {
          input: {
            height: densityConfig.inputHeight.md,
          },
        },
      },
      Button: {
        styles: {
          root: {
            height: densityConfig.inputHeight.md,
          },
        },
      },
    },
  });

  return (
    <ThemeContext.Provider
      value={{
        palette,
        colorScheme,
        density,
        setPalette,
        setColorScheme,
        setDensity,
        toggleColorScheme,
      }}
    >
      <MantineProvider theme={theme} forceColorScheme={colorScheme}>
        <ModalsProvider>
          <Notifications position="top-right" zIndex={9999} />
          {children}
        </ModalsProvider>
      </MantineProvider>
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
}
