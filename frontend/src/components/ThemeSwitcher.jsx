import { useState } from 'react'
import { Palette, Check } from '@phosphor-icons/react'
import './ThemeSwitcher.css'

const THEMES = [
  { 
    id: 'dark', 
    name: 'Dark', 
    vars: {
      '--bg-primary': '#0A0E14',
      '--bg-secondary': '#161B22',
      '--bg-tertiary': '#1F2428',
      '--text-primary': '#E6EDF3',
      '--text-secondary': '#8B949E',
      '--accent-primary': '#3B82F6',
      '--border': '#30363D'
    }
  },
  { 
    id: 'light', 
    name: 'Light', 
    vars: {
      '--bg-primary': '#FFFFFF',
      '--bg-secondary': '#F8FAFC',
      '--bg-tertiary': '#F1F5F9',
      '--text-primary': '#0F172A',
      '--text-secondary': '#64748B',
      '--accent-primary': '#3B82F6',
      '--border': '#E2E8F0'
    }
  },
  { 
    id: 'blue', 
    name: 'Ocean Blue', 
    vars: {
      '--bg-primary': '#0C1E2E',
      '--bg-secondary': '#142A3E',
      '--bg-tertiary': '#1A3548',
      '--text-primary': '#E0F2FE',
      '--text-secondary': '#7DD3FC',
      '--accent-primary': '#0EA5E9',
      '--border': '#1E3A52'
    }
  },
  { 
    id: 'green', 
    name: 'Forest Green', 
    vars: {
      '--bg-primary': '#0A1F14',
      '--bg-secondary': '#0F2A1C',
      '--bg-tertiary': '#143624',
      '--text-primary': '#DCFCE7',
      '--text-secondary': '#86EFAC',
      '--accent-primary': '#10B981',
      '--border': '#1F4A30'
    }
  },
  { 
    id: 'purple', 
    name: 'Royal Purple', 
    vars: {
      '--bg-primary': '#1A0F2E',
      '--bg-secondary': '#25163E',
      '--bg-tertiary': '#301D4E',
      '--text-primary': '#F3E8FF',
      '--text-secondary': '#C4B5FD',
      '--accent-primary': '#8B5CF6',
      '--border': '#3E2A5C'
    }
  },
  { 
    id: 'orange', 
    name: 'Sunset Orange', 
    vars: {
      '--bg-primary': '#2E1A05',
      '--bg-secondary': '#3E250A',
      '--bg-tertiary': '#4E300F',
      '--text-primary': '#FEF3C7',
      '--text-secondary': '#FCD34D',
      '--accent-primary': '#F59E0B',
      '--border': '#5E3A14'
    }
  },
]

export default function ThemeSwitcher({ isOpen, onClose }) {
  const [current, setCurrent] = useState(() => {
    return localStorage.getItem('ucm-theme') || 'dark'
  })
  
  function handleThemeChange(themeId) {
    setCurrent(themeId)
    const theme = THEMES.find(t => t.id === themeId)
    if (theme) {
      // Apply all CSS variables
      Object.entries(theme.vars).forEach(([key, value]) => {
        document.documentElement.style.setProperty(key, value)
      })
      localStorage.setItem('ucm-theme', themeId)
    }
  }
  
  if (!isOpen) return null
  
  return (
    <div className="theme-switcher-overlay" onClick={onClose}>
      <div className="theme-switcher" onClick={e => e.stopPropagation()}>
        <div className="theme-header">
          <Palette size={24} weight="duotone" />
          <h3>Choose Theme</h3>
        </div>
        
        <div className="theme-grid">
          {THEMES.map(theme => (
            <button
              key={theme.id}
              className={`theme-option ${current === theme.id ? 'active' : ''}`}
              onClick={() => handleThemeChange(theme.id)}
            >
              <div className="theme-preview" style={{ 
                background: theme.vars['--bg-primary'],
                borderColor: theme.vars['--accent-primary']
              }}>
                <div className="preview-dot" style={{ background: theme.vars['--accent-primary'] }}></div>
                <div className="preview-bar" style={{ background: theme.vars['--accent-primary'] }}></div>
              </div>
              <span className="theme-name">{theme.name}</span>
              {current === theme.id && <Check size={18} weight="bold" className="check" />}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
