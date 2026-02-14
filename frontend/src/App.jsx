import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { AuthProvider, ThemeProvider, NotificationProvider, MobileProvider, useAuth } from './contexts'
import { AppShell, ErrorBoundary, LoadingSpinner, SessionWarning, ForcePasswordChange, SafeModeOverlay } from './components'

// Auto-reload on chunk load failure (stale cache after update)
function lazyWithRetry(importFn) {
  return lazy(() => importFn().catch(() => {
    // Chunk failed to load (likely 404 after update) — reload once
    const key = 'chunk_reload'
    if (!sessionStorage.getItem(key)) {
      sessionStorage.setItem(key, '1')
      window.location.reload()
    }
    sessionStorage.removeItem(key)
    return importFn()
  }))
}

// Lazy load pages for code splitting
const LoginPage = lazyWithRetry(() => import('./pages/LoginPage'))
const ForgotPasswordPage = lazyWithRetry(() => import('./pages/ForgotPasswordPage'))
const ResetPasswordPage = lazyWithRetry(() => import('./pages/ResetPasswordPage'))
const DashboardPage = lazyWithRetry(() => import('./pages/DashboardPage'))
const CertificatesPage = lazyWithRetry(() => import('./pages/CertificatesPage'))
const CAsPage = lazyWithRetry(() => import('./pages/CAsPage'))
const CSRsPage = lazyWithRetry(() => import('./pages/CSRsPage'))
const TemplatesPage = lazyWithRetry(() => import('./pages/TemplatesPage'))
const UsersGroupsPage = lazyWithRetry(() => import('./pages/UsersGroupsPage'))
const ACMEPage = lazyWithRetry(() => import('./pages/ACMEPage'))
const SCEPPage = lazyWithRetry(() => import('./pages/SCEPPage'))
const SettingsPage = lazyWithRetry(() => import('./pages/SettingsPage'))
const OperationsPage = lazyWithRetry(() => import('./pages/OperationsPage'))
const CertificateToolsPage = lazyWithRetry(() => import('./pages/CertificateToolsPage'))
const AccountPage = lazyWithRetry(() => import('./pages/AccountPage'))
const AuditLogsPage = lazyWithRetry(() => import('./pages/AuditLogsPage'))
const CRLOCSPPage = lazyWithRetry(() => import('./pages/CRLOCSPPage'))
const TrustStorePage = lazyWithRetry(() => import('./pages/TrustStorePage'))
const RBACPage = lazyWithRetry(() => import('./pages/RBACPage'))
const HSMPage = lazyWithRetry(() => import('./pages/HSMPage'))

// Loading fallback for lazy components
function PageLoader() {
  return (
    <div className="flex items-center justify-center h-full min-h-[400px]">
      <LoadingSpinner size="lg" />
    </div>
  )
}

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()
  
  if (loading) {
    return <PageLoader />
  }
  
  return isAuthenticated ? children : <Navigate to="/login" replace />
}

function AppRoutes() {
  const { isAuthenticated, forcePasswordChange, clearForcePasswordChange, logout } = useAuth()
  
  return (
    <Suspense fallback={<PageLoader />}>
      {/* Global session warning (when logged in) */}
      {isAuthenticated && <SessionWarning onLogout={logout} />}
      
      {/* Force password change modal */}
      {isAuthenticated && forcePasswordChange && (
        <ForcePasswordChange onComplete={clearForcePasswordChange} />
      )}
      
      <Routes>
        <Route 
          path="/login" 
          element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />} 
        />
        <Route 
          path="/login/sso-complete" 
          element={<LoginPage />} 
        />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        
        <Route element={<AppShell />}>
          <Route path="/" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="/certificates" element={<ProtectedRoute><CertificatesPage /></ProtectedRoute>} />
          <Route path="/certificates/:id" element={<ProtectedRoute><CertificatesPage /></ProtectedRoute>} />
          <Route path="/cas" element={<ProtectedRoute><CAsPage /></ProtectedRoute>} />
          <Route path="/cas/:id" element={<ProtectedRoute><CAsPage /></ProtectedRoute>} />
          <Route path="/csrs" element={<ProtectedRoute><CSRsPage /></ProtectedRoute>} />
          <Route path="/templates" element={<ProtectedRoute><TemplatesPage /></ProtectedRoute>} />
          <Route path="/users" element={<ProtectedRoute><UsersGroupsPage /></ProtectedRoute>} />
          <Route path="/acme" element={<ProtectedRoute><ACMEPage /></ProtectedRoute>} />
          <Route path="/scep-config" element={<ProtectedRoute><SCEPPage /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
          <Route path="/audit" element={<ProtectedRoute><AuditLogsPage /></ProtectedRoute>} />
          <Route path="/operations" element={<ProtectedRoute><OperationsPage /></ProtectedRoute>} />
          <Route path="/import" element={<Navigate to="/operations" replace />} />
          <Route path="/tools" element={<ProtectedRoute><CertificateToolsPage /></ProtectedRoute>} />
          <Route path="/account" element={<ProtectedRoute><AccountPage /></ProtectedRoute>} />
          <Route path="/crl-ocsp" element={<ProtectedRoute><CRLOCSPPage /></ProtectedRoute>} />
          <Route path="/truststore" element={<ProtectedRoute><TrustStorePage /></ProtectedRoute>} />
          <Route path="/truststore/:id" element={<ProtectedRoute><TrustStorePage /></ProtectedRoute>} />
          
          {/* Security & Administration */}
          <Route path="/groups" element={<Navigate to="/users?tab=groups" replace />} />
          <Route path="/rbac" element={<ProtectedRoute><RBACPage /></ProtectedRoute>} />
          <Route path="/sso" element={<Navigate to="/settings?tab=sso" replace />} />
          <Route path="/hsm" element={<ProtectedRoute><HSMPage /></ProtectedRoute>} />
          <Route path="/security" element={<Navigate to="/settings?tab=security" replace />} />
        </Route>
        
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <BrowserRouter>
          <AuthProvider>
            <NotificationProvider>
              <MobileProvider>
                <SafeModeOverlay />
                <AppRoutes />
              </MobileProvider>
            </NotificationProvider>
          </AuthProvider>
        </BrowserRouter>
      </ThemeProvider>
    </ErrorBoundary>
  )
}
