import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import CAs from './pages/CAs'
import Certificates from './pages/Certificates'
import CSRs from './pages/CSRs'
import Settings from './pages/Settings'
import Users from './pages/Users'
import ACME from './pages/ACME'
import CRL from './pages/CRL'
import SCEP from './pages/SCEP'
import Templates from './pages/Templates'
import TrustStore from './pages/TrustStore'
import Account from './pages/Account'
import AppShell from './components/AppShell'

// Theme definitions (must match ThemeSwitcher.jsx)
const THEMES = {
  'dark': {
    '--bg-primary': '#0A0E14',
    '--bg-secondary': '#161B22',
    '--bg-tertiary': '#1F2428',
    '--text-primary': '#E6EDF3',
    '--text-secondary': '#8B949E',
    '--accent-primary': '#3B82F6',
    '--border': '#30363D'
  },
  'light': {
    '--bg-primary': '#FFFFFF',
    '--bg-secondary': '#F8FAFC',
    '--bg-tertiary': '#F1F5F9',
    '--text-primary': '#0F172A',
    '--text-secondary': '#64748B',
    '--accent-primary': '#3B82F6',
    '--border': '#E2E8F0'
  },
  'blue': {
    '--bg-primary': '#0C1E2E',
    '--bg-secondary': '#142A3E',
    '--bg-tertiary': '#1A3548',
    '--text-primary': '#E0F2FE',
    '--text-secondary': '#7DD3FC',
    '--accent-primary': '#0EA5E9',
    '--border': '#1E3A52'
  },
  'green': {
    '--bg-primary': '#0A1F14',
    '--bg-secondary': '#0F2A1C',
    '--bg-tertiary': '#143624',
    '--text-primary': '#DCFCE7',
    '--text-secondary': '#86EFAC',
    '--accent-primary': '#10B981',
    '--border': '#1F4A30'
  },
  'purple': {
    '--bg-primary': '#1A0F2E',
    '--bg-secondary': '#25163E',
    '--bg-tertiary': '#301D4E',
    '--text-primary': '#F3E8FF',
    '--text-secondary': '#C4B5FD',
    '--accent-primary': '#8B5CF6',
    '--border': '#3E2A5C'
  },
  'orange': {
    '--bg-primary': '#2E1A05',
    '--bg-secondary': '#3E250A',
    '--bg-tertiary': '#4E300F',
    '--text-primary': '#FEF3C7',
    '--text-secondary': '#FCD34D',
    '--accent-primary': '#F59E0B',
    '--border': '#5E3A14'
  }
}

export default function App() {
  // Load saved theme on mount
  useEffect(() => {
    const savedTheme = localStorage.getItem('ucm-theme') || 'dark'
    const themeVars = THEMES[savedTheme]
    if (themeVars) {
      Object.entries(themeVars).forEach(([key, value]) => {
        document.documentElement.style.setProperty(key, value)
      })
    }
  }, [])
  
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<AppShell />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="cas" element={<CAs />} />
          <Route path="certificates" element={<Certificates />} />
          <Route path="csrs" element={<CSRs />} />
          <Route path="settings" element={<Settings />} />
          <Route path="users" element={<Users />} />
          <Route path="acme" element={<ACME />} />
          <Route path="crl" element={<CRL />} />
          <Route path="scep" element={<SCEP />} />
          <Route path="templates" element={<Templates />} />
          <Route path="truststore" element={<TrustStore />} />
          <Route path="account" element={<Account />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
