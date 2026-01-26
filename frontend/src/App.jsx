import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppShell from './components/AppShell'
import Dashboard from './pages/Dashboard'
import CAs from './pages/CAs'
import Login from './pages/Login'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={
          <AppShell>
            <Dashboard />
          </AppShell>
        } />
        <Route path="/dashboard" element={
          <AppShell>
            <Dashboard />
          </AppShell>
        } />
        <Route path="/cas" element={
          <AppShell>
            <CAs />
          </AppShell>
        } />
      </Routes>
    </BrowserRouter>
  )
}
