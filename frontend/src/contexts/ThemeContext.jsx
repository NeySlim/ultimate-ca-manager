import { createContext, useContext, useState, useEffect, useCallback } from 'react'

// Theme families with integrated icon colors
// Icon colors are theme-aware to avoid "ton sur ton" conflicts
const themeFamilies = {
  gray: {
    id: 'gray',
    name: 'Gray',
    accent: '#4F8EF7',
    dark: {
      'bg-primary': '#12161C',
      'bg-secondary': '#1C222A',
      'bg-tertiary': '#252D38',
      'text-primary': '#F0F4F8',
      'text-secondary': '#A8B4C4',
      'text-tertiary': '#7E8A9A',
      'accent-primary': '#4F8EF7',
      'accent-success': '#34D399',
      'accent-warning': '#FBBF24',
      'accent-danger': '#F87171',
      'accent-pro': '#A78BFA',
      'border': '#3A4555',
      'gradient-from': '#4F8EF7',
      'gradient-to': '#A78BFA',
      'gradient-accent': 'linear-gradient(135deg, #4F8EF7 0%, #A78BFA 100%)',
      'gradient-bg': 'linear-gradient(145deg, #1e2633 0%, #252035 50%, #1e2633 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(79,142,247,0.08), rgba(167,139,250,0.04), transparent)',
      'detail-header-border': 'rgba(255,255,255,0.06)',
      'detail-header-shadow': 'inset 0 1px 0 0 rgba(255,255,255,0.04)',
      'detail-icon-bg': 'linear-gradient(135deg, #4F8EF7, rgba(79,142,247,0.7))',
      'detail-icon-shadow': '0 4px 12px rgba(79,142,247,0.25)',
      'detail-stats-border': 'rgba(255,255,255,0.06)',
      'detail-section-bg': 'rgba(28,34,42,0.6)',
      'detail-section-border': '#3A4555',
      'detail-field-bg': 'rgba(255,255,255,0.02)',
      'detail-field-border': 'rgba(255,255,255,0.05)',
      // Icon colors - standard
      'icon-orange-bg': 'rgba(249, 115, 22, 0.15)',
      'icon-orange-text': '#FB923C',
      'icon-amber-bg': 'rgba(245, 158, 11, 0.15)',
      'icon-amber-text': '#FBBF24',
      'icon-emerald-bg': 'rgba(52, 211, 153, 0.15)',
      'icon-emerald-text': '#34D399',
      'icon-blue-bg': 'rgba(79, 142, 247, 0.15)',
      'icon-blue-text': '#60A5FA',
      'icon-violet-bg': 'rgba(139, 92, 246, 0.15)',
      'icon-violet-text': '#A78BFA',
      'icon-teal-bg': 'rgba(20, 184, 166, 0.15)',
      'icon-teal-text': '#2DD4BF',
    },
    light: {
      'bg-primary': '#EFF2F7',
      'bg-secondary': '#FFFFFF',
      'bg-tertiary': '#E4E8EF',
      'text-primary': '#111827',
      'text-secondary': '#4B5563',
      'text-tertiary': '#6B7280',
      'accent-primary': '#2563EB',
      'accent-success': '#059669',
      'accent-warning': '#D97706',
      'accent-danger': '#DC2626',
      'accent-pro': '#7C3AED',
      'border': '#CBD5E1',
      'gradient-from': '#2563EB',
      'gradient-to': '#7C3AED',
      'gradient-accent': 'linear-gradient(135deg, #2563EB 0%, #7C3AED 100%)',
      'gradient-bg': 'linear-gradient(145deg, #EFF2F7 0%, #E8EDFB 50%, #EFF2F7 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(37,99,235,0.10), rgba(124,58,237,0.06), rgba(255,255,255,0.95))',
      'detail-header-border': 'rgba(37,99,235,0.12)',
      'detail-header-shadow': '0 1px 3px rgba(37,99,235,0.10)',
      'detail-icon-bg': 'linear-gradient(135deg, #2563EB, #4F46E5)',
      'detail-icon-shadow': '0 4px 14px rgba(37,99,235,0.30)',
      'detail-stats-border': 'rgba(0,0,0,0.08)',
      'detail-section-bg': '#F1F5F9',
      'detail-section-border': '#CBD5E1',
      'detail-field-bg': 'rgba(0,0,0,0.035)',
      'detail-field-border': 'rgba(0,0,0,0.08)',
      // Icon colors - stronger/deeper for light mode
      'icon-orange-bg': 'rgba(234, 88, 12, 0.12)',
      'icon-orange-text': '#C2410C',
      'icon-amber-bg': 'rgba(217, 119, 6, 0.12)',
      'icon-amber-text': '#B45309',
      'icon-emerald-bg': 'rgba(5, 150, 105, 0.12)',
      'icon-emerald-text': '#047857',
      'icon-blue-bg': 'rgba(37, 99, 235, 0.12)',
      'icon-blue-text': '#1D4ED8',
      'icon-violet-bg': 'rgba(124, 58, 237, 0.12)',
      'icon-violet-text': '#6D28D9',
      'icon-teal-bg': 'rgba(13, 148, 136, 0.12)',
      'icon-teal-text': '#0F766E',
    }
  },
  purple: {
    id: 'purple',
    name: 'Purple Night',
    accent: '#A855F7',
    dark: {
      'bg-primary': '#1A0B2E',
      'bg-secondary': '#251438',
      'bg-tertiary': '#301E47',
      'text-primary': '#F3E8FF',
      'text-secondary': '#D4C5E9',
      'text-tertiary': '#AB9AC8',
      'accent-primary': '#A855F7',
      'accent-success': '#22C55E',
      'accent-warning': '#F59E0B',
      'accent-danger': '#F43F5E',
      'accent-pro': '#EC4899',
      'border': '#442B66',
      'gradient-from': '#A855F7',
      'gradient-to': '#EC4899',
      'gradient-accent': 'linear-gradient(135deg, #A855F7 0%, #EC4899 100%)',
      'gradient-bg': 'linear-gradient(135deg, #3d2555 0%, #4a1942 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(168,85,247,0.08), rgba(236,72,153,0.04), transparent)',
      'detail-header-border': 'rgba(255,255,255,0.06)',
      'detail-header-shadow': 'inset 0 1px 0 0 rgba(255,255,255,0.04)',
      'detail-icon-bg': 'linear-gradient(135deg, #A855F7, rgba(168,85,247,0.7))',
      'detail-icon-shadow': '0 4px 12px rgba(168,85,247,0.25)',
      'detail-stats-border': 'rgba(255,255,255,0.06)',
      'detail-section-bg': 'rgba(37,20,56,0.6)',
      'detail-section-border': '#442B66',
      'detail-field-bg': 'rgba(255,255,255,0.02)',
      'detail-field-border': 'rgba(255,255,255,0.05)',
      // Icon colors - avoid violet/pink, use teal/cyan
      'icon-orange-bg': 'rgba(249, 115, 22, 0.35)',
      'icon-orange-text': '#FB923C',
      'icon-amber-bg': 'rgba(245, 158, 11, 0.35)',
      'icon-amber-text': '#FBBF24',
      'icon-emerald-bg': 'rgba(52, 211, 153, 0.15)',
      'icon-emerald-text': '#34D399',
      'icon-blue-bg': 'rgba(20, 184, 166, 0.15)',  // Teal instead
      'icon-blue-text': '#2DD4BF',
      'icon-violet-bg': 'rgba(20, 184, 166, 0.15)', // Teal instead
      'icon-violet-text': '#2DD4BF',
      'icon-teal-bg': 'rgba(52, 211, 153, 0.15)',  // Green
      'icon-teal-text': '#34D399',
    },
    light: {
      'bg-primary': '#F0EBF8',
      'bg-secondary': '#FFFFFF',
      'bg-tertiary': '#E8DFF5',
      'text-primary': '#3B0764',
      'text-secondary': '#6B21A8',
      'text-tertiary': '#7C3AED',
      'accent-primary': '#A855F7',
      'accent-success': '#22C55E',
      'accent-warning': '#F59E0B',
      'accent-danger': '#F43F5E',
      'accent-pro': '#EC4899',
      'border': '#D8B4FE',
      'gradient-from': '#A855F7',
      'gradient-to': '#EC4899',
      'gradient-accent': 'linear-gradient(135deg, #A855F7 0%, #EC4899 100%)',
      'gradient-bg': 'linear-gradient(145deg, #F0EBF8 0%, #EDE4FA 50%, #F0EBF8 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(168,85,247,0.12), rgba(236,72,153,0.06), rgba(255,255,255,0.95))',
      'detail-header-border': 'rgba(168,85,247,0.18)',
      'detail-header-shadow': '0 1px 3px rgba(168,85,247,0.12)',
      'detail-icon-bg': 'linear-gradient(135deg, #A855F7, #EC4899)',
      'detail-icon-shadow': '0 4px 14px rgba(168,85,247,0.30)',
      'detail-stats-border': 'rgba(168,85,247,0.12)',
      'detail-section-bg': 'rgba(243,232,255,0.6)',
      'detail-section-border': '#D8B4FE',
      'detail-field-bg': 'rgba(168,85,247,0.035)',
      'detail-field-border': 'rgba(168,85,247,0.12)',
      // Icon colors - avoid violet/pink
      'icon-orange-bg': 'rgba(234, 88, 12, 0.12)',
      'icon-orange-text': '#C2410C',
      'icon-amber-bg': 'rgba(217, 119, 6, 0.12)',
      'icon-amber-text': '#B45309',
      'icon-emerald-bg': 'rgba(5, 150, 105, 0.12)',
      'icon-emerald-text': '#047857',
      'icon-blue-bg': 'rgba(13, 148, 136, 0.12)',  // Teal
      'icon-blue-text': '#0F766E',
      'icon-violet-bg': 'rgba(13, 148, 136, 0.12)', // Teal
      'icon-violet-text': '#0F766E',
      'icon-teal-bg': 'rgba(5, 150, 105, 0.12)',
      'icon-teal-text': '#047857',
    }
  },
  sunset: {
    id: 'sunset',
    name: 'Orange Sunset',
    accent: '#F97316',
    dark: {
      'bg-primary': '#1F0F0A',
      'bg-secondary': '#2A1510',
      'bg-tertiary': '#3A1F16',
      'text-primary': '#FFF4ED',
      'text-secondary': '#D9A688',
      'text-tertiary': '#B88A6B',
      'accent-primary': '#F97316',
      'accent-success': '#22C55E',
      'accent-warning': '#FBBF24',
      'accent-danger': '#DC2626',
      'accent-pro': '#A855F7',
      'border': '#4D2815',
      'gradient-from': '#F97316',
      'gradient-to': '#DC2626',
      'gradient-accent': 'linear-gradient(135deg, #F97316 0%, #DC2626 100%)',
      'gradient-bg': 'linear-gradient(135deg, #4a2618 0%, #5c1a1a 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(249,115,22,0.08), rgba(220,38,38,0.04), transparent)',
      'detail-header-border': 'rgba(255,255,255,0.06)',
      'detail-header-shadow': 'inset 0 1px 0 0 rgba(255,255,255,0.04)',
      'detail-icon-bg': 'linear-gradient(135deg, #F97316, rgba(249,115,22,0.7))',
      'detail-icon-shadow': '0 4px 12px rgba(249,115,22,0.25)',
      'detail-stats-border': 'rgba(255,255,255,0.06)',
      'detail-section-bg': 'rgba(42,21,16,0.6)',
      'detail-section-border': '#4D2815',
      'detail-field-bg': 'rgba(255,255,255,0.02)',
      'detail-field-border': 'rgba(255,255,255,0.05)',
      // Icon colors - avoid orange/amber, use blue/teal
      'icon-orange-bg': 'rgba(59, 130, 246, 0.15)',  // Blue instead
      'icon-orange-text': '#60A5FA',
      'icon-amber-bg': 'rgba(20, 184, 166, 0.15)',  // Teal instead
      'icon-amber-text': '#2DD4BF',
      'icon-emerald-bg': 'rgba(52, 211, 153, 0.15)',
      'icon-emerald-text': '#34D399',
      'icon-blue-bg': 'rgba(59, 130, 246, 0.15)',
      'icon-blue-text': '#60A5FA',
      'icon-violet-bg': 'rgba(139, 92, 246, 0.15)',
      'icon-violet-text': '#A78BFA',
      'icon-teal-bg': 'rgba(20, 184, 166, 0.15)',
      'icon-teal-text': '#2DD4BF',
    },
    light: {
      'bg-primary': '#F5EDE5',
      'bg-secondary': '#FFFFFF',
      'bg-tertiary': '#FDDCB5',
      'text-primary': '#611705',
      'text-secondary': '#9A3412',
      'text-tertiary': '#C2410C',
      'accent-primary': '#EA580C',
      'accent-success': '#22C55E',
      'accent-warning': '#FBBF24',
      'accent-danger': '#DC2626',
      'accent-pro': '#A855F7',
      'border': '#FDBA74',
      'gradient-from': '#F97316',
      'gradient-to': '#EA580C',
      'gradient-accent': 'linear-gradient(135deg, #F97316 0%, #EA580C 100%)',
      'gradient-bg': 'linear-gradient(145deg, #F5EDE5 0%, #FDE8D0 50%, #F5EDE5 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(249,115,22,0.12), rgba(234,88,12,0.06), rgba(255,255,255,0.95))',
      'detail-header-border': 'rgba(249,115,22,0.18)',
      'detail-header-shadow': '0 1px 3px rgba(249,115,22,0.12)',
      'detail-icon-bg': 'linear-gradient(135deg, #F97316, #EA580C)',
      'detail-icon-shadow': '0 4px 14px rgba(249,115,22,0.30)',
      'detail-stats-border': 'rgba(249,115,22,0.12)',
      'detail-section-bg': 'rgba(255,237,213,0.6)',
      'detail-section-border': '#FDBA74',
      'detail-field-bg': 'rgba(249,115,22,0.035)',
      'detail-field-border': 'rgba(249,115,22,0.12)',
      // Icon colors - avoid orange/amber
      'icon-orange-bg': 'rgba(37, 99, 235, 0.12)',  // Blue
      'icon-orange-text': '#1D4ED8',
      'icon-amber-bg': 'rgba(13, 148, 136, 0.12)',  // Teal
      'icon-amber-text': '#0F766E',
      'icon-emerald-bg': 'rgba(5, 150, 105, 0.12)',
      'icon-emerald-text': '#047857',
      'icon-blue-bg': 'rgba(37, 99, 235, 0.12)',
      'icon-blue-text': '#1D4ED8',
      'icon-violet-bg': 'rgba(124, 58, 237, 0.12)',
      'icon-violet-text': '#6D28D9',
      'icon-teal-bg': 'rgba(13, 148, 136, 0.12)',
      'icon-teal-text': '#0F766E',
    }
  },
}

const ThemeContext = createContext()

export function ThemeProvider({ children }) {
  const [themeFamily, setThemeFamily] = useState('gray')
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
    const savedFamily = localStorage.getItem('ucm-theme-family')
    const savedMode = localStorage.getItem('ucm-theme-mode')
    
    if (savedFamily && themeFamilies[savedFamily]) {
      setThemeFamily(savedFamily)
    }
    if (savedMode && ['system', 'dark', 'light'].includes(savedMode)) {
      setMode(savedMode)
    }
  }, [])

  // Apply theme colors
  useEffect(() => {
    const family = themeFamilies[themeFamily]
    if (family) {
      const colors = family[resolvedMode]
      Object.entries(colors).forEach(([key, value]) => {
        document.documentElement.style.setProperty(`--${key}`, value)
      })
      localStorage.setItem('ucm-theme-family', themeFamily)
      localStorage.setItem('ucm-theme-mode', mode)
    }
  }, [themeFamily, resolvedMode, mode])

  const currentTheme = `${themeFamily}-${resolvedMode}`
  const setCurrentTheme = useCallback((themeId) => {
    if (themeFamilies[themeId]) {
      setThemeFamily(themeId)
    } else if (themeId === 'dark') {
      setThemeFamily('gray')
      setMode('dark')
    } else if (themeId === 'light') {
      setThemeFamily('gray')
      setMode('light')
    }
  }, [])

  const themes = Object.values(themeFamilies)
  const isLight = resolvedMode === 'light'

  return (
    <ThemeContext.Provider value={{ 
      themeFamily,
      setThemeFamily,
      mode,
      setMode,
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
