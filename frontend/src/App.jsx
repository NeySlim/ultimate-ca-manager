import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { AuthProvider, ThemeProvider, NotificationProvider, useAuth } from './contexts'
import { AppShell, ErrorBoundary, LoadingSpinner } from './components'

// Lazy load pages for code splitting
const LoginPage = lazy(() => import('./pages/LoginPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const CertificatesPage = lazy(() => import('./pages/CertificatesPage'))
const CAsPage = lazy(() => import('./pages/CAsPage'))
const CSRsPage = lazy(() => import('./pages/CSRsPage'))
const TemplatesPage = lazy(() => import('./pages/TemplatesPage'))
const UsersPage = lazy(() => import('./pages/UsersPage'))
const ACMEPage = lazy(() => import('./pages/ACMEPage'))
const SCEPPage = lazy(() => import('./pages/SCEPPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const ImportExportPage = lazy(() => import('./pages/ImportExportPage'))
const AccountPage = lazy(() => import('./pages/AccountPage'))
const AuditLogsPage = lazy(() => import('./pages/AuditLogsPage'))

// Pro pages - lazy load with graceful fallback
const GroupsPage = lazy(() => 
  import('./pro/pages/GroupsPage').catch(() => ({ default: () => <Navigate to="/" replace /> }))
)
const RBACPage = lazy(() => 
  import('./pro/pages/RBACPage').catch(() => ({ default: () => <Navigate to="/" replace /> }))
)
const SSOPage = lazy(() => 
  import('./pro/pages/SSOPage').catch(() => ({ default: () => <Navigate to="/" replace /> }))
)
const HSMPage = lazy(() => 
  import('./pro/pages/HSMPage').catch(() => ({ default: () => <Navigate to="/" replace /> }))
)

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
  const { isAuthenticated } = useAuth()
  
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route 
          path="/login" 
          element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />} 
        />
        
        <Route element={<AppShell />}>
          <Route path="/" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="/certificates" element={<ProtectedRoute><CertificatesPage /></ProtectedRoute>} />
          <Route path="/cas" element={<ProtectedRoute><CAsPage /></ProtectedRoute>} />
          <Route path="/csrs" element={<ProtectedRoute><CSRsPage /></ProtectedRoute>} />
          <Route path="/templates" element={<ProtectedRoute><TemplatesPage /></ProtectedRoute>} />
          <Route path="/users" element={<ProtectedRoute><UsersPage /></ProtectedRoute>} />
          <Route path="/acme" element={<ProtectedRoute><ACMEPage /></ProtectedRoute>} />
          <Route path="/scep" element={<ProtectedRoute><SCEPPage /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
          <Route path="/audit" element={<ProtectedRoute><AuditLogsPage /></ProtectedRoute>} />
          <Route path="/import" element={<ProtectedRoute><ImportExportPage /></ProtectedRoute>} />
          <Route path="/account" element={<ProtectedRoute><AccountPage /></ProtectedRoute>} />
          
          {/* Pro Routes */}
          <Route path="/groups" element={<ProtectedRoute><GroupsPage /></ProtectedRoute>} />
          <Route path="/rbac" element={<ProtectedRoute><RBACPage /></ProtectedRoute>} />
          <Route path="/sso" element={<ProtectedRoute><SSOPage /></ProtectedRoute>} />
          <Route path="/hsm" element={<ProtectedRoute><HSMPage /></ProtectedRoute>} />
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
              <AppRoutes />
            </NotificationProvider>
          </AuthProvider>
        </BrowserRouter>
      </ThemeProvider>
    </ErrorBoundary>
  )
}
