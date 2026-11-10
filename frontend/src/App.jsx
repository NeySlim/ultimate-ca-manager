import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Suspense } from 'react'
import { AuthProvider, ThemeProvider, NotificationProvider, MobileProvider, InspectorProvider, useAuth } from './contexts'
import { WebSocketProvider } from './hooks/useWebSocket'
import { MODULES, REDIRECTS } from './navigation/registry'
import { loginUrl } from './navigation/safeNext'
import { pages, lazyWithRetry } from './navigation/pages'
import { AppShell, ErrorBoundary, LoadingSpinner, SessionWarning, ForcePasswordChange, ForceEnroll2FA, SafeModeOverlay, InspectorDock } from './components'

// Lazy load pages for code splitting (module pages are bound in navigation/pages.js)
const LoginPage = lazyWithRetry(() => import('./pages/LoginPage'))
const ForgotPasswordPage = lazyWithRetry(() => import('./pages/ForgotPasswordPage'))
const ResetPasswordPage = lazyWithRetry(() => import('./pages/ResetPasswordPage'))
const DevShowcasePage = lazyWithRetry(() => import('./pages/DevShowcasePage'))

// Loading fallback for lazy components
function PageLoader() {
  return (
    <div className="flex items-center justify-center h-full min-h-[400px]">
      <LoadingSpinner size="lg" />
    </div>
  )
}

function ProtectedRoute({ children }) {
  const { pathname, search } = useLocation()
  const toLogin = loginUrl(pathname, search)
  const { isAuthenticated, loading } = useAuth()
  
  if (loading) {
    return <PageLoader />
  }
  
  return isAuthenticated ? children : <Navigate to={toLogin} replace />
}

function AdminRoute({ children }) {
  const { pathname, search } = useLocation()
  const toLogin = loginUrl(pathname, search)
  const { isAuthenticated, loading, permissions } = useAuth()
  
  if (loading) return <PageLoader />
  if (!isAuthenticated) return <Navigate to={toLogin} replace />
  if (!permissions?.includes('*')) return <Navigate to="/" replace />
  
  return children
}

function PermissionRoute({ children, permission }) {
  const { pathname, search } = useLocation()
  const toLogin = loginUrl(pathname, search)
  const { isAuthenticated, loading, permissions } = useAuth()
  
  if (loading) return <PageLoader />
  if (!isAuthenticated) return <Navigate to={toLogin} replace />
  if (permissions?.includes('*')) return children
  if (permission && !permissions?.includes(permission)) return <Navigate to="/" replace />
  
  return children
}

export function guarded(guard, element) {
  if (guard === 'admin') return <AdminRoute>{element}</AdminRoute>
  if (guard && guard.permission) return <PermissionRoute permission={guard.permission}>{element}</PermissionRoute>
  if (guard === 'auth') return <ProtectedRoute>{element}</ProtectedRoute>
  // A mistyped guard must not open the route to every signed-in user
  throw new Error(`navigation: unknown guard ${JSON.stringify(guard)}`)
}

// Routes of every registry module and legacy redirect, under the app shell
export function moduleRoutes() {
  const routes = []
  for (const m of MODULES) {
    const Page = pages[m.id]
    if (!Page) throw new Error(`navigation: no page bound to module '${m.id}'`)
    for (const path of [m.path, ...m.paths]) {
      routes.push(<Route key={path} path={path} element={guarded(m.guard, <Page />)} />)
    }
  }
  for (const r of REDIRECTS) {
    routes.push(<Route key={r.from} path={r.from} element={<Navigate to={r.to} replace />} />)
  }
  return routes
}

export function AppRoutes() {
  const { isAuthenticated, loading, sessionChecked, forcePasswordChange, clearForcePasswordChange, mustEnroll2fa, checkSession, logout } = useAuth()
  const { pathname } = useLocation()
  const gated = isAuthenticated && (mustEnroll2fa || forcePasswordChange)

  return (
    <Suspense fallback={<PageLoader />}>
      {/* Global session warning (when logged in) */}
      {isAuthenticated && <SessionWarning onLogout={logout} />}

      {/* Mandatory 2FA enrolment overlay (#141) — takes precedence over the
          password-change prompt; blocks all access until TOTP is confirmed. */}
      {isAuthenticated && mustEnroll2fa && (
        <ForceEnroll2FA onComplete={checkSession} />
      )}

      {/* Force password change modal */}
      {isAuthenticated && !mustEnroll2fa && forcePasswordChange && (
        <ForcePasswordChange onComplete={clearForcePasswordChange} />
      )}

      {/* Pages mount once the gates lift: the server refuses their requests until then.
          A login URL is left now, or a logout from the prompt would land back on it. */}
      {gated && pathname.startsWith('/login') && <Navigate to="/" replace />}
      {!gated && <Routes>
        <Route 
          path="/login" 
          element={
            loading ? <PageLoader /> :
            isAuthenticated ? <Navigate to="/" replace /> : 
            <LoginPage />
          } 
        />
        <Route 
          path="/login/sso-complete" 
          element={<LoginPage />} 
        />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        
        <Route element={<AppShell />}>
          {moduleRoutes()}
          {/* Component showcase: accessible by URL only, not a module */}
          <Route path="/dev/components" element={<ProtectedRoute><DevShowcasePage /></ProtectedRoute>} />
        </Route>
        
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>}
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
            <WebSocketProvider>
              <MobileProvider>
                <InspectorProvider>
                  <SafeModeOverlay />
                  <AppRoutes />
                  <InspectorDock />
                </InspectorProvider>
              </MobileProvider>
            </WebSocketProvider>
            </NotificationProvider>
          </AuthProvider>
        </BrowserRouter>
      </ThemeProvider>
    </ErrorBoundary>
  )
}
