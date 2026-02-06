import { createContext, useContext, useState, useEffect, useCallback } from 'react'

// Theme families - each has dark and light variant
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
    },
    light: {
      'bg-primary': '#F7F8FA',
      'bg-secondary': '#FFFFFF',
      'bg-tertiary': '#EEF0F4',
      'text-primary': '#1A202C',
      'text-secondary': '#4A5568',
      'text-tertiary': '#718096',
      'accent-primary': '#3B82F6',
      'accent-success': '#10B981',
      'accent-warning': '#F59E0B',
      'accent-danger': '#EF4444',
      'accent-pro': '#8B5CF6',
      'border': '#E2E8F0',
      'gradient-from': '#3B82F6',
      'gradient-to': '#8B5CF6',
      'gradient-accent': 'linear-gradient(135deg, #3B82F6 0%, #8B5CF6 100%)',
      'gradient-bg': 'linear-gradient(145deg, #F7F8FA 0%, #F0F4FF 50%, #F7F8FA 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(59,130,246,0.08), rgba(139,92,246,0.05), rgba(255,255,255,0.9))',
      'detail-header-border': 'rgba(0,0,0,0.08)',
      'detail-header-shadow': '0 1px 3px rgba(0,0,0,0.08)',
      'detail-icon-bg': 'linear-gradient(135deg, #3B82F6, #6366F1)',
      'detail-icon-shadow': '0 4px 12px rgba(59,130,246,0.25)',
      'detail-stats-border': 'rgba(0,0,0,0.08)',
      'detail-section-bg': 'rgba(241,245,249,0.7)',
      'detail-section-border': '#E2E8F0',
      'detail-field-bg': 'rgba(0,0,0,0.02)',
      'detail-field-border': 'rgba(0,0,0,0.06)',
    }
  },
  ocean: {
    id: 'ocean',
    name: 'Blue Ocean',
    accent: '#0EA5E9',
    dark: {
      'bg-primary': '#0A1628',
      'bg-secondary': '#0F1E35',
      'bg-tertiary': '#162842',
      'text-primary': '#E1F0FF',
      'text-secondary': '#8BB7E9',
      'text-tertiary': '#6A9AC8',
      'accent-primary': '#0EA5E9',
      'accent-success': '#10B981',
      'accent-warning': '#F59E0B',
      'accent-danger': '#EF4444',
      'accent-pro': '#8B5CF6',
      'border': '#1E3A5F',
      'gradient-from': '#0EA5E9',
      'gradient-to': '#06B6D4',
      'gradient-accent': 'linear-gradient(135deg, #0EA5E9 0%, #06B6D4 100%)',
      'gradient-bg': 'linear-gradient(135deg, #0d2d4f 0%, #1a4d6d 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(14,165,233,0.08), rgba(6,182,212,0.04), transparent)',
      'detail-header-border': 'rgba(255,255,255,0.06)',
      'detail-header-shadow': 'inset 0 1px 0 0 rgba(255,255,255,0.04)',
      'detail-icon-bg': 'linear-gradient(135deg, #0EA5E9, rgba(14,165,233,0.7))',
      'detail-icon-shadow': '0 4px 12px rgba(14,165,233,0.25)',
      'detail-stats-border': 'rgba(255,255,255,0.06)',
      'detail-section-bg': 'rgba(15,30,53,0.6)',
      'detail-section-border': '#1E3A5F',
      'detail-field-bg': 'rgba(255,255,255,0.02)',
      'detail-field-border': 'rgba(255,255,255,0.05)',
    },
    light: {
      'bg-primary': '#F0F9FF',
      'bg-secondary': '#FFFFFF',
      'bg-tertiary': '#E0F2FE',
      'text-primary': '#0C4A6E',
      'text-secondary': '#0369A1',
      'text-tertiary': '#0284C7',
      'accent-primary': '#0EA5E9',
      'accent-success': '#10B981',
      'accent-warning': '#F59E0B',
      'accent-danger': '#EF4444',
      'accent-pro': '#8B5CF6',
      'border': '#BAE6FD',
      'gradient-from': '#0EA5E9',
      'gradient-to': '#06B6D4',
      'gradient-accent': 'linear-gradient(135deg, #0EA5E9 0%, #06B6D4 100%)',
      'gradient-bg': 'linear-gradient(145deg, #F0F9FF 0%, #E0F2FE 50%, #F0F9FF 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(14,165,233,0.1), rgba(6,182,212,0.05), rgba(255,255,255,0.9))',
      'detail-header-border': 'rgba(14,165,233,0.15)',
      'detail-header-shadow': '0 1px 3px rgba(14,165,233,0.1)',
      'detail-icon-bg': 'linear-gradient(135deg, #0EA5E9, #06B6D4)',
      'detail-icon-shadow': '0 4px 12px rgba(14,165,233,0.25)',
      'detail-stats-border': 'rgba(14,165,233,0.15)',
      'detail-section-bg': 'rgba(224,242,254,0.5)',
      'detail-section-border': '#BAE6FD',
      'detail-field-bg': 'rgba(14,165,233,0.03)',
      'detail-field-border': 'rgba(14,165,233,0.1)',
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
    },
    light: {
      'bg-primary': '#FAF5FF',
      'bg-secondary': '#FFFFFF',
      'bg-tertiary': '#F3E8FF',
      'text-primary': '#581C87',
      'text-secondary': '#7C3AED',
      'text-tertiary': '#8B5CF6',
      'accent-primary': '#A855F7',
      'accent-success': '#22C55E',
      'accent-warning': '#F59E0B',
      'accent-danger': '#F43F5E',
      'accent-pro': '#EC4899',
      'border': '#E9D5FF',
      'gradient-from': '#A855F7',
      'gradient-to': '#EC4899',
      'gradient-accent': 'linear-gradient(135deg, #A855F7 0%, #EC4899 100%)',
      'gradient-bg': 'linear-gradient(145deg, #FAF5FF 0%, #F3E8FF 50%, #FAF5FF 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(168,85,247,0.1), rgba(236,72,153,0.05), rgba(255,255,255,0.9))',
      'detail-header-border': 'rgba(168,85,247,0.15)',
      'detail-header-shadow': '0 1px 3px rgba(168,85,247,0.1)',
      'detail-icon-bg': 'linear-gradient(135deg, #A855F7, #EC4899)',
      'detail-icon-shadow': '0 4px 12px rgba(168,85,247,0.25)',
      'detail-stats-border': 'rgba(168,85,247,0.15)',
      'detail-section-bg': 'rgba(243,232,255,0.5)',
      'detail-section-border': '#E9D5FF',
      'detail-field-bg': 'rgba(168,85,247,0.03)',
      'detail-field-border': 'rgba(168,85,247,0.1)',
    }
  },
  forest: {
    id: 'forest',
    name: 'Green Forest',
    accent: '#10B981',
    dark: {
      'bg-primary': '#0A1910',
      'bg-secondary': '#0F2418',
      'bg-tertiary': '#153020',
      'text-primary': '#E8F5E9',
      'text-secondary': '#7FA98F',
      'text-tertiary': '#5D8A6D',
      'accent-primary': '#10B981',
      'accent-success': '#4ADE80',
      'accent-warning': '#F59E0B',
      'accent-danger': '#EF4444',
      'accent-pro': '#A855F7',
      'border': '#1E4D2B',
      'gradient-from': '#10B981',
      'gradient-to': '#059669',
      'gradient-accent': 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
      'gradient-bg': 'linear-gradient(135deg, #1a3d2a 0%, #0d5231 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(16,185,129,0.08), rgba(5,150,105,0.04), transparent)',
      'detail-header-border': 'rgba(255,255,255,0.06)',
      'detail-header-shadow': 'inset 0 1px 0 0 rgba(255,255,255,0.04)',
      'detail-icon-bg': 'linear-gradient(135deg, #10B981, rgba(16,185,129,0.7))',
      'detail-icon-shadow': '0 4px 12px rgba(16,185,129,0.25)',
      'detail-stats-border': 'rgba(255,255,255,0.06)',
      'detail-section-bg': 'rgba(15,36,24,0.6)',
      'detail-section-border': '#1E4D2B',
      'detail-field-bg': 'rgba(255,255,255,0.02)',
      'detail-field-border': 'rgba(255,255,255,0.05)',
    },
    light: {
      'bg-primary': '#F0FDF4',
      'bg-secondary': '#FFFFFF',
      'bg-tertiary': '#DCFCE7',
      'text-primary': '#14532D',
      'text-secondary': '#166534',
      'text-tertiary': '#15803D',
      'accent-primary': '#10B981',
      'accent-success': '#4ADE80',
      'accent-warning': '#F59E0B',
      'accent-danger': '#EF4444',
      'accent-pro': '#A855F7',
      'border': '#BBF7D0',
      'gradient-from': '#10B981',
      'gradient-to': '#059669',
      'gradient-accent': 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
      'gradient-bg': 'linear-gradient(145deg, #F0FDF4 0%, #DCFCE7 50%, #F0FDF4 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(16,185,129,0.1), rgba(5,150,105,0.05), rgba(255,255,255,0.9))',
      'detail-header-border': 'rgba(16,185,129,0.15)',
      'detail-header-shadow': '0 1px 3px rgba(16,185,129,0.1)',
      'detail-icon-bg': 'linear-gradient(135deg, #10B981, #059669)',
      'detail-icon-shadow': '0 4px 12px rgba(16,185,129,0.25)',
      'detail-stats-border': 'rgba(16,185,129,0.15)',
      'detail-section-bg': 'rgba(220,252,231,0.5)',
      'detail-section-border': '#BBF7D0',
      'detail-field-bg': 'rgba(16,185,129,0.03)',
      'detail-field-border': 'rgba(16,185,129,0.1)',
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
    },
    light: {
      'bg-primary': '#FFF7ED',
      'bg-secondary': '#FFFFFF',
      'bg-tertiary': '#FFEDD5',
      'text-primary': '#7C2D12',
      'text-secondary': '#C2410C',
      'text-tertiary': '#EA580C',
      'accent-primary': '#F97316',
      'accent-success': '#22C55E',
      'accent-warning': '#FBBF24',
      'accent-danger': '#DC2626',
      'accent-pro': '#A855F7',
      'border': '#FED7AA',
      'gradient-from': '#F97316',
      'gradient-to': '#EA580C',
      'gradient-accent': 'linear-gradient(135deg, #F97316 0%, #EA580C 100%)',
      'gradient-bg': 'linear-gradient(145deg, #FFF7ED 0%, #FFEDD5 50%, #FFF7ED 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(249,115,22,0.1), rgba(234,88,12,0.05), rgba(255,255,255,0.9))',
      'detail-header-border': 'rgba(249,115,22,0.15)',
      'detail-header-shadow': '0 1px 3px rgba(249,115,22,0.1)',
      'detail-icon-bg': 'linear-gradient(135deg, #F97316, #EA580C)',
      'detail-icon-shadow': '0 4px 12px rgba(249,115,22,0.25)',
      'detail-stats-border': 'rgba(249,115,22,0.15)',
      'detail-section-bg': 'rgba(255,237,213,0.5)',
      'detail-section-border': '#FED7AA',
      'detail-field-bg': 'rgba(249,115,22,0.03)',
      'detail-field-border': 'rgba(249,115,22,0.1)',
    }
  },
  cyber: {
    id: 'cyber',
    name: 'Cyber Pink',
    accent: '#EC4899',
    dark: {
      'bg-primary': '#0D0221',
      'bg-secondary': '#190933',
      'bg-tertiary': '#240B3E',
      'text-primary': '#FFE5F8',
      'text-secondary': '#D89FCC',
      'text-tertiary': '#B87DAA',
      'accent-primary': '#EC4899',
      'accent-success': '#22C55E',
      'accent-warning': '#F59E0B',
      'accent-danger': '#F43F5E',
      'accent-pro': '#8B5CF6',
      'border': '#3D1754',
      'gradient-from': '#EC4899',
      'gradient-to': '#F472B6',
      'gradient-accent': 'linear-gradient(135deg, #EC4899 0%, #F472B6 100%)',
      'gradient-bg': 'linear-gradient(135deg, #3d1854 0%, #5a1359 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(236,72,153,0.08), rgba(244,114,182,0.04), transparent)',
      'detail-header-border': 'rgba(255,255,255,0.06)',
      'detail-header-shadow': 'inset 0 1px 0 0 rgba(255,255,255,0.04)',
      'detail-icon-bg': 'linear-gradient(135deg, #EC4899, rgba(236,72,153,0.7))',
      'detail-icon-shadow': '0 4px 12px rgba(236,72,153,0.25)',
      'detail-stats-border': 'rgba(255,255,255,0.06)',
      'detail-section-bg': 'rgba(25,9,51,0.6)',
      'detail-section-border': '#3D1754',
      'detail-field-bg': 'rgba(255,255,255,0.02)',
      'detail-field-border': 'rgba(255,255,255,0.05)',
    },
    light: {
      'bg-primary': '#FDF2F8',
      'bg-secondary': '#FFFFFF',
      'bg-tertiary': '#FCE7F3',
      'text-primary': '#831843',
      'text-secondary': '#BE185D',
      'text-tertiary': '#DB2777',
      'accent-primary': '#EC4899',
      'accent-success': '#22C55E',
      'accent-warning': '#F59E0B',
      'accent-danger': '#F43F5E',
      'accent-pro': '#8B5CF6',
      'border': '#FBCFE8',
      'gradient-from': '#EC4899',
      'gradient-to': '#F472B6',
      'gradient-accent': 'linear-gradient(135deg, #EC4899 0%, #F472B6 100%)',
      'gradient-bg': 'linear-gradient(145deg, #FDF2F8 0%, #FCE7F3 50%, #FDF2F8 100%)',
      'detail-header-bg': 'linear-gradient(135deg, rgba(236,72,153,0.1), rgba(244,114,182,0.05), rgba(255,255,255,0.9))',
      'detail-header-border': 'rgba(236,72,153,0.15)',
      'detail-header-shadow': '0 1px 3px rgba(236,72,153,0.1)',
      'detail-icon-bg': 'linear-gradient(135deg, #EC4899, #F472B6)',
      'detail-icon-shadow': '0 4px 12px rgba(236,72,153,0.25)',
      'detail-stats-border': 'rgba(236,72,153,0.15)',
      'detail-section-bg': 'rgba(252,231,243,0.5)',
      'detail-section-border': '#FBCFE8',
      'detail-field-bg': 'rgba(236,72,153,0.03)',
      'detail-field-border': 'rgba(236,72,153,0.1)',
    }
  }
}

const ThemeContext = createContext()

export function ThemeProvider({ children }) {
  // Theme family (gray, ocean, purple, etc.)
  const [themeFamily, setThemeFamily] = useState('gray')
  // Mode: 'system' | 'dark' | 'light'
  const [mode, setMode] = useState('system')
  // Resolved dark/light based on mode and system preference
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
      // Save preferences
      localStorage.setItem('ucm-theme-family', themeFamily)
      localStorage.setItem('ucm-theme-mode', mode)
    }
  }, [themeFamily, resolvedMode, mode])

  // For backwards compatibility
  const currentTheme = `${themeFamily}-${resolvedMode}`
  const setCurrentTheme = useCallback((themeId) => {
    // Handle old theme IDs (dark, light, ocean, purple, etc.)
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

  // Expose theme families as array for UI
  const themes = Object.values(themeFamilies)
  
  const isLight = resolvedMode === 'light'

  return (
    <ThemeContext.Provider value={{ 
      // New API
      themeFamily,
      setThemeFamily,
      mode,
      setMode,
      resolvedMode,
      isLight,
      themes,
      themeFamilies,
      // Legacy API
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
