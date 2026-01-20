import React, { createContext, useContext, useState } from 'react';

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
