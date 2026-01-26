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
    // STRICT: Use design-system.html colors
    if (colorScheme === 'dark') {
      root.style.setProperty('--bg-app', '#1a1a1a');  // design-system.html --bg-primary
      root.style.setProperty('--bg-panel', '#1e1e1e'); // design-system.html --bg-secondary
      root.style.setProperty('--bg-surface', '#252525'); // design-system.html --bg-tertiary
      root.style.setProperty('--bg-element', '#2a2a2a'); // design-system.html --bg-hover
      root.style.setProperty('--bg-element-hover', '#333333');
      root.style.setProperty('--border-color', '#333333'); // design-system.html --border-primary
      root.style.setProperty('--text-primary', '#e8e8e8'); // design-system.html
      root.style.setProperty('--text-secondary', '#cccccc'); // design-system.html
      root.style.setProperty('--text-muted', '#888888'); // design-system.html --text-tertiary
    } else {
      // SOFT LIGHT THEME (less bright)
      root.style.setProperty('--bg-app', '#e8eaed');     /* Soft grey */
      root.style.setProperty('--bg-panel', '#f5f6f7');   /* Light grey */
      root.style.setProperty('--bg-surface', '#fafbfc'); /* Almost white */
      root.style.setProperty('--bg-element', '#f0f1f3'); /* Light element */
      root.style.setProperty('--bg-element-hover', '#e2e4e8');
      root.style.setProperty('--border-color', '#e2e4e8');
      root.style.setProperty('--text-primary', '#1a1d23');   /* Soft black */
      root.style.setProperty('--text-secondary', '#4a5568'); /* Softer grey */
      root.style.setProperty('--text-muted', '#718096');     /* Medium grey */
    }
    
    // Apply Density Variables
    // STRICT: Force design-system.html values (26px buttons, 30px inputs, 3px radius, 13px font)
    const densitySettings = {
      compact: {
        '--control-height': '22px',  // btn-sm from design-system.html
        '--control-padding-x': '8px',
        '--control-radius': '3px',   // STRICT: always 3px
        '--font-size-control': '11px',
        '--table-spacing': '6px',
        '--table-font-size': '11px',
        '--icon-size': '14px',
      },
      normal: {
        '--control-height': '26px',  // STRICT from design-system.html
        '--control-padding-x': '12px', // STRICT from design-system.html
        '--control-radius': '3px',   // STRICT: always 3px
        '--font-size-control': '13px', // STRICT from design-system.html
        '--table-spacing': '8px',    // STRICT from design-system.html
        '--table-font-size': '13px',  // STRICT from design-system.html
        '--icon-size': '16px',
      },
      comfortable: {
        '--control-height': '32px',  // btn-lg from design-system.html
        '--control-padding-x': '16px',
        '--control-radius': '3px',   // STRICT: always 3px
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

  // Alias for accent color (used by TopBar theme selector)
  const setAccentColor = (color) => {
    const root = document.documentElement;
    root.style.setProperty('--accent-primary', color);
    root.style.setProperty('--accent-gradient-start', color);
    // Save to palette if it matches
    const matchingPalette = Object.entries(colorPalettes).find(
      ([_, p]) => p.primary === color
    )?.[0];
    if (matchingPalette) {
      setPalette(matchingPalette);
    }
  };

  const accentColor = colorPalettes[palette]?.primary || '#5a8fc7';

  return (
    <ThemeContext.Provider value={{
      palette,
      setPalette,
      colorScheme,
      setColorScheme,
      density,
      setDensity,
      accentColor,
      setAccentColor,
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
