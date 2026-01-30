import { createContext, useContext, useState, useEffect } from 'react'

const themes = {
  dark: {
    id: 'dark',
    name: 'Dark Gray',
    colors: {
      'bg-primary': '#12161C',
      'bg-secondary': '#1C222A',
      'bg-tertiary': '#252D38',
      'text-primary': '#F0F4F8',
      'text-secondary': '#9CA8B8',
      'text-tertiary': '#6E7A8A',
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
    }
  },
  ocean: {
    id: 'ocean',
    name: 'Blue Ocean',
    colors: {
      'bg-primary': '#0A1628',
      'bg-secondary': '#0F1E35',
      'bg-tertiary': '#162842',
      'text-primary': '#E1F0FF',
      'text-secondary': '#7BA7D9',
      'text-tertiary': '#5A8AB8',
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
    }
  },
  purple: {
    id: 'purple',
    name: 'Purple Night',
    colors: {
      'bg-primary': '#1A0B2E',
      'bg-secondary': '#251438',
      'bg-tertiary': '#301E47',
      'text-primary': '#F3E8FF',
      'text-secondary': '#C4B5D9',
      'text-tertiary': '#9B8AB8',
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
    }
  },
  forest: {
    id: 'forest',
    name: 'Green Forest',
    colors: {
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
    }
  },
  sunset: {
    id: 'sunset',
    name: 'Orange Sunset',
    colors: {
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
    }
  },
  cyber: {
    id: 'cyber',
    name: 'Cyber Pink',
    colors: {
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
    }
  }
}

const ThemeContext = createContext()

export function ThemeProvider({ children }) {
  const [currentTheme, setCurrentTheme] = useState('dark')
  
  useEffect(() => {
    const saved = localStorage.getItem('ucm-theme')
    if (saved && themes[saved]) {
      setCurrentTheme(saved)
    }
  }, [])
  
  useEffect(() => {
    const theme = themes[currentTheme]
    if (theme) {
      Object.entries(theme.colors).forEach(([key, value]) => {
        document.documentElement.style.setProperty(`--${key}`, value)
      })
      localStorage.setItem('ucm-theme', currentTheme)
    }
  }, [currentTheme])
  
  return (
    <ThemeContext.Provider value={{ currentTheme, setCurrentTheme, themes }}>
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
