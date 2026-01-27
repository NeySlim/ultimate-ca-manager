import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, ThemeProvider, NotificationProvider, useAuth } from './contexts'
import { AppShell } from './components'
import {
  LoginPage,
  DashboardPage,
  CertificatesPage,
  CAsPage,
  CSRsPage,
  TemplatesPage,
  UsersPage,
  ACMEPage,
  SettingsPage,
  ImportExportPage,
  AccountPage,
} from './pages'

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()
  
  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-bg-primary">
        <div className="text-text-secondary">Loading...</div>
      </div>
    )
  }
  
  return isAuthenticated ? children : <Navigate to="/login" replace />
}

function AppRoutes() {
  const { isAuthenticated } = useAuth()
  
  return (
    <Routes>
      <Route 
        path="/login" 
        element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />} 
      />
      
      <Route element={<AppShell />}>
        <Route path="/" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
        <Route path="/certificates" element={<ProtectedRoute><CertificatesPage /></ProtectedRoute>} />
        <Route path="/cas" element={<ProtectedRoute><CAsPage /></ProtectedRoute>} />
        <Route path="/csrs" element={<ProtectedRoute><CSRsPage /></ProtectedRoute>} />
        <Route path="/templates" element={<ProtectedRoute><TemplatesPage /></ProtectedRoute>} />
        <Route path="/users" element={<ProtectedRoute><UsersPage /></ProtectedRoute>} />
        <Route path="/acme" element={<ProtectedRoute><ACMEPage /></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
        <Route path="/import" element={<ProtectedRoute><ImportExportPage /></ProtectedRoute>} />
        <Route path="/account" element={<ProtectedRoute><AccountPage /></ProtectedRoute>} />
      </Route>
      
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <NotificationProvider>
            <AppRoutes />
          </NotificationProvider>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  )
}
