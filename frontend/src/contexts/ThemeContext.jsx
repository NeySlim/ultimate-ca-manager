import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { subscribePreferences, persistPreference, getPreferences } from '../stores/userPreferencesStore'

// Colours live in styles/tokens.css, selected by data-theme / data-mode on <html>.
// Here only what the pickers need: id, label key and a per-mode preview (surface, accent).
const themeFamilies = {
  atelier: {
    id: 'atelier',
    name: 'Atelier',
    nameKey: 'settings.themeFamilies.atelier',
    swatch: {
      dark: { surface: '#233143', accent: '#94bfff' },
      light: { surface: '#eaf0f6', accent: '#245bb1' },
    },
  },
  aurore: {
    id: 'aurore',
    name: 'Aurore',
    nameKey: 'settings.themeFamilies.aurore',
    swatch: {
      dark: { surface: '#1a2036', accent: '#a5b4ff' },
      light: { surface: '#eef0f8', accent: '#3742bd' },
    },
  },
  purple: {
    id: 'purple',
    name: 'Purple Night',
    nameKey: 'settings.themeFamilies.purple',
    swatch: {
      dark: { surface: '#301E47', accent: '#A855F7' },
      light: { surface: '#E8DFF5', accent: '#9a3ff0' },
    },
  },
  sunset: {
    id: 'sunset',
    name: 'Orange Sunset',
    nameKey: 'settings.themeFamilies.sunset',
    swatch: {
      dark: { surface: '#3A1F16', accent: '#F97316' },
      light: { surface: '#FDDCB5', accent: '#cd4d0b' },
    },
  },
}

// Preferences stored before the rename ('gray') read as 'atelier'.
const normalizeFamily = (id) => {
  const family = id === 'gray' ? 'atelier' : id
  return Object.prototype.hasOwnProperty.call(themeFamilies, family) ? family : null
}

const ThemeContext = createContext()

export function ThemeProvider({ children }) {
  const [themeFamily, setThemeFamily] = useState('atelier')
  const [mode, setMode] = useState('system')
  const [resolvedMode, setResolvedMode] = useState('dark')

  // Listen to system preference changes
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    
    const updateResolvedMode = () => {
      if (mode === 'system') {
        setResolvedMode(mediaQuery.matches ? 'dark' : 'light')
      } else {
        setResolvedMode(mode)
      }
    }
    
    updateResolvedMode()
    mediaQuery.addEventListener('change', updateResolvedMode)
    return () => mediaQuery.removeEventListener('change', updateResolvedMode)
  }, [mode])

  // Load saved preferences
  useEffect(() => {
    try {
      const savedFamily = localStorage.getItem('ucm-theme-family')
      const savedMode = localStorage.getItem('ucm-theme-mode')
      
      const family = normalizeFamily(savedFamily)
      if (family) {
        setThemeFamily(family)
      }
      if (savedMode && ['system', 'dark', 'light'].includes(savedMode)) {
        setMode(savedMode)
      }
    } catch {
      // localStorage unavailable (private browsing)
    }
  }, [])

  // Apply theme: the palette is CSS, keyed on these two attributes.
  useEffect(() => {
    const root = document.documentElement
    root.setAttribute('data-theme', themeFamily)
    root.setAttribute('data-mode', resolvedMode)
    try {
      localStorage.setItem('ucm-theme-family', themeFamily)
      localStorage.setItem('ucm-theme-mode', mode)
    } catch {
      // localStorage unavailable
    }
  }, [themeFamily, resolvedMode, mode])

  // Server-side preferences (issue #73): on each prefs change, sync local
  // theme state. Triggered when AuthContext applies values from the server.
  useEffect(() => {
    const apply = (prefs) => {
      const family = normalizeFamily(prefs.theme_family)
      if (family) {
        setThemeFamily(prev => prev !== family ? family : prev)
      }
      if (prefs.theme_mode && ['system', 'dark', 'light'].includes(prefs.theme_mode)) {
        setMode(prev => prev !== prefs.theme_mode ? prefs.theme_mode : prev)
      }
    }
    apply(getPreferences())
    return subscribePreferences(apply)
  }, [])

  // Wrap setters so user changes propagate to the server when authenticated.
  const setThemeFamilyAndPersist = useCallback((value) => {
    setThemeFamily(value)
    persistPreference('theme_family', value)
  }, [])
  const setModeAndPersist = useCallback((value) => {
    setMode(value)
    persistPreference('theme_mode', value)
  }, [])

  const currentTheme = `${themeFamily}-${resolvedMode}`
  const setCurrentTheme = useCallback((themeId) => {
    if (normalizeFamily(themeId)) {
      setThemeFamilyAndPersist(normalizeFamily(themeId))
    } else if (themeId === 'dark') {
      setThemeFamilyAndPersist('atelier')
      setModeAndPersist('dark')
    } else if (themeId === 'light') {
      setThemeFamilyAndPersist('atelier')
      setModeAndPersist('light')
    }
  }, [setThemeFamilyAndPersist, setModeAndPersist])

  // Pickers show the accent actually applied in the resolved mode.
  const themes = Object.values(themeFamilies).map((f) => ({ ...f, accent: f.swatch[resolvedMode].accent }))
  const isLight = resolvedMode === 'light'

  return (
    <ThemeContext.Provider value={{ 
      themeFamily,
      setThemeFamily: setThemeFamilyAndPersist,
      mode,
      setMode: setModeAndPersist,
      resolvedMode,
      isLight,
      themes,
      themeFamilies,
      currentTheme,
      setCurrentTheme
    }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider')
  }
  return context
}
