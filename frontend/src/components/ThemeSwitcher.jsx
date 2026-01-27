import { useState } from 'react'
import { Palette, Check } from '@phosphor-icons/react'
import './ThemeSwitcher.css'

const THEMES = [
  { id: 'dark', name: 'Dark', primary: '#3B82F6', bg: '#0F1419' },
  { id: 'light', name: 'Light', primary: '#3B82F6', bg: '#FFFFFF' },
  { id: 'blue', name: 'Ocean Blue', primary: '#0EA5E9', bg: '#0C1E2E' },
  { id: 'green', name: 'Forest Green', primary: '#10B981', bg: '#0A1F14' },
  { id: 'purple', name: 'Royal Purple', primary: '#8B5CF6', bg: '#1A0F2E' },
  { id: 'orange', name: 'Sunset Orange', primary: '#F59E0B', bg: '#2E1A05' },
]

export default function ThemeSwitcher({ isOpen, onClose }) {
  const [current, setCurrent] = useState('dark')
  
  function handleThemeChange(themeId) {
    setCurrent(themeId)
    const theme = THEMES.find(t => t.id === themeId)
    if (theme) {
      document.documentElement.style.setProperty('--primary', theme.primary)
      document.documentElement.style.setProperty('--background', theme.bg)
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
                background: theme.bg,
                borderColor: theme.primary 
              }}>
                <div className="preview-dot" style={{ background: theme.primary }}></div>
                <div className="preview-bar" style={{ background: theme.primary }}></div>
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
