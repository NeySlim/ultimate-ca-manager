/**
 * 🎭 THEME PROVIDER
 * Global theme context with CSS variables injection
 */

import React, { createContext, useContext, useState, useEffect } from 'react';
import {
  getColorVariables,
  getTypographyVariables,
  getSpacingVariables,
  getShadowVariables,
  getAnimationVariables,
} from '../foundations';

const ThemeContext = createContext({ theme: 'dark', toggleTheme: () => {} });

export function useTheme() {
  return useContext(ThemeContext);
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    try {
      const stored = localStorage.getItem('ucm-theme');
      if (stored === 'dark' || stored === 'light') return stored;
    } catch (e) {}
    
    try {
      if (window.matchMedia?.('(prefers-color-scheme: light)').matches) {
        return 'light';
      }
    } catch (e) {}
    
    return 'dark';
  });

  const toggleTheme = () => {
    setTheme(prev => {
      const next = prev === 'dark' ? 'light' : 'dark';
      try {
        localStorage.setItem('ucm-theme', next);
      } catch (e) {}
      return next;
    });
  };

  useEffect(() => {
    const root = document.documentElement;
    
    const vars = {
      ...getColorVariables(theme),
      ...getTypographyVariables(),
      ...getSpacingVariables(),
      ...getShadowVariables(theme),
      ...getAnimationVariables(),
    };

    Object.entries(vars).forEach(([key, value]) => {
      root.style.setProperty(key, value);
    });
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
