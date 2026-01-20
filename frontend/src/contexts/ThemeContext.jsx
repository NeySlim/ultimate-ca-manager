import React, { createContext, useContext, useState } from 'react';

import { colorPalettes } from '../theme/colors';

const ThemeContext = createContext(undefined);

export const ThemeProvider = ({ children }) => {
  const [palette, setPaletteState] = useState(() => {
    return localStorage.getItem('ucm-palette') || 'teal';
  });

  const [colorScheme, setColorSchemeState] = useState(() => {
    return localStorage.getItem('ucm-color-scheme') || 'dark';
  });

  const [density, setDensityState] = useState(() => {
    return localStorage.getItem('ucm-density') || 'normal';
  });

  // Apply CSS variables when palette changes
  React.useEffect(() => {
    const root = document.documentElement;
    const selectedPalette = colorPalettes[palette] || colorPalettes.teal;
    
    root.style.setProperty('--accent-primary', selectedPalette.primary);
    root.style.setProperty('--accent-secondary', selectedPalette.light);
    root.style.setProperty('--accent-hover', selectedPalette.hover);
    root.style.setProperty('--accent-gradient-start', selectedPalette.primary);
    root.style.setProperty('--accent-gradient-end', selectedPalette.light);

    // Apply Background/Surface variables based on Color Scheme
    if (colorScheme === 'dark') {
      root.style.setProperty('--bg-app', '#1a1b1e');
      root.style.setProperty('--bg-panel', '#25262b');
      root.style.setProperty('--bg-surface', '#141517');
      root.style.setProperty('--bg-element', '#2c2e33');
      root.style.setProperty('--bg-element-hover', '#373a40');
      root.style.setProperty('--border-color', '#373a40');
      root.style.setProperty('--text-primary', '#c1c2c5');
      root.style.setProperty('--text-secondary', '#909296');
      root.style.setProperty('--text-muted', '#5c5f66');
    } else {
      root.style.setProperty('--bg-app', '#eef0f2'); /* Darker grey for contrast */
      root.style.setProperty('--bg-panel', '#ffffff'); /* Pure white panels */
      root.style.setProperty('--bg-surface', '#ffffff'); /* White content backgrounds */
      root.style.setProperty('--bg-element', '#f8f9fa'); /* Light grey elements */
      root.style.setProperty('--bg-element-hover', '#e9ecef');
      root.style.setProperty('--border-color', '#dee2e6');
      root.style.setProperty('--text-primary', '#1f2937');
      root.style.setProperty('--text-secondary', '#4b5563');
      root.style.setProperty('--text-muted', '#9ca3af');
    }
    
    // Apply Density Variables
    const densitySettings = {
      compact: {
        '--control-height': '24px',
        '--control-padding-x': '8px',
        '--control-radius': '2px',
        '--font-size-control': '12px',
        '--table-spacing': '4px',
        '--table-font-size': '12px',
        '--icon-size': '14px',
      },
      normal: {
        '--control-height': '28px',
        '--control-padding-x': '12px',
        '--control-radius': '3px',
        '--font-size-control': '13px',
        '--table-spacing': '8px',
        '--table-font-size': '13px',
        '--icon-size': '16px',
      },
      comfortable: {
        '--control-height': '36px',
        '--control-padding-x': '16px',
        '--control-radius': '6px',
        '--font-size-control': '14px',
        '--table-spacing': '12px',
        '--table-font-size': '14px',
        '--icon-size': '18px',
      }
    };

    const currentDensity = densitySettings[density] || densitySettings.normal;
    Object.entries(currentDensity).forEach(([key, value]) => {
      root.style.setProperty(key, value);
    });

    // Also update Mantine's color scheme attribute for CSS specificity
    root.setAttribute('data-mantine-color-scheme', colorScheme);
  }, [palette, colorScheme, density]);

  const setPalette = (newPalette) => {
    setPaletteState(newPalette);
    localStorage.setItem('ucm-palette', newPalette);
  };

  const setColorScheme = (scheme) => {
    setColorSchemeState(scheme);
    localStorage.setItem('ucm-color-scheme', scheme);
  };

  const setDensity = (newDensity) => {
    setDensityState(newDensity);
    localStorage.setItem('ucm-density', newDensity);
    
    // Force direct update without waiting for effect
    const root = document.documentElement;
    const densitySettings = {
      compact: {
        '--control-height': '24px',
        '--control-padding-x': '8px',
        '--control-radius': '2px',
        '--font-size-control': '12px',
        '--table-spacing': '4px',
        '--table-font-size': '12px',
        '--icon-size': '14px',
      },
      normal: {
        '--control-height': '28px',
        '--control-padding-x': '12px',
        '--control-radius': '3px',
        '--font-size-control': '13px',
        '--table-spacing': '8px',
        '--table-font-size': '13px',
        '--icon-size': '16px',
      },
      comfortable: {
        '--control-height': '36px',
        '--control-padding-x': '16px',
        '--control-radius': '6px',
        '--font-size-control': '14px',
        '--table-spacing': '12px',
        '--table-font-size': '14px',
        '--icon-size': '18px',
      }
    };
    const currentDensity = densitySettings[newDensity] || densitySettings.normal;
    Object.entries(currentDensity).forEach(([key, value]) => {
      root.style.setProperty(key, value);
    });
  };

  return (
    <ThemeContext.Provider value={{
      palette,
      setPalette,
      colorScheme,
      setColorScheme,
      density,
      setDensity,
    }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) throw new Error('useTheme must be used within ThemeProvider');
  return context;
};
