import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom'
import { Suspense } from 'react'
import { AuthProvider, ThemeProvider, NotificationProvider, MobileProvider, InspectorProvider, useAuth } from './contexts'
import { WebSocketProvider } from './hooks/useWebSocket'
import { MODULES, REDIRECTS } from './navigation/registry'
import { loginUrl, safeNext } from './navigation/safeNext'
import { pages, lazyWithRetry, GuidePage } from './navigation/pages'
import { isServedPage, servedAtBoot } from './lib/servedPage'
import { AppShell, ErrorBoundary, LoadingSpinner, SessionWarning, ForcePasswordChange, ForceEnroll2FA, SafeModeOverlay, InspectorCloseOnNavigate } from './components'

// Lazy load pages for code splitting (module pages are bound in navigation/pages.js)
const LoginPage = lazyWithRetry(() => import('./pages/LoginPage'))
const ForgotPasswordPage = lazyWithRetry(() => import('./pages/ForgotPasswordPage'))
const ResetPasswordPage = lazyWithRetry(() => import('./pages/ResetPasswordPage'))
// The Atelier gabarits drawn with the mockup's records: a development build only (dev server, or `vite build --mode gabarits`)
const GABARITS = import.meta.env.DEV || import.meta.env.MODE === 'gabarits'
const GabaritsPage = GABARITS ? lazyWithRetry(() => import('./pages/dev/GabaritsPage')) : null
const SsoTestCompletePage = lazyWithRetry(() => import('./pages/SsoTestCompletePage'))
const SsoTestLaunchPage = lazyWithRetry(() => import('./pages/SsoTestLaunchPage'))

// Loading fallback for lazy components
function PageLoader() {
  return (
    <div className="flex items-center justify-center h-full min-h-[400px]">
      <LoadingSpinner size="lg" />
    </div>
  )
}

// Signed in on the sign-in page: the page its ?next= names (checked), else the landing page
function SignedIn() {
  const { search } = useLocation()
  return <Navigate to={safeNext(new URLSearchParams(search).get('next')) || '/'} replace />
}

function ProtectedRoute({ children }) {
  const { pathname, search, hash } = useLocation()
  const toLogin = loginUrl(pathname, search, hash)
  const { isAuthenticated, loading, sessionChecked } = useAuth()
  
  if (loading) {
    // The page the server drew for a valid session stays while the session is first checked
    return !sessionChecked && isServedPage(pathname) ? children : <PageLoader />
  }
  
  return isAuthenticated ? children : <Navigate to={toLogin} replace />
}

function AdminRoute({ children }) {
  const { pathname, search, hash } = useLocation()
  const toLogin = loginUrl(pathname, search, hash)
  const { isAuthenticated, loading, permissions } = useAuth()
  
  if (loading) return <PageLoader />
  if (!isAuthenticated) return <Navigate to={toLogin} replace />
  if (!permissions?.includes('*')) return <Navigate to="/" replace />
  
  return children
}

function PermissionRoute({ children, permission }) {
  const { pathname, search, hash } = useLocation()
  const toLogin = loginUrl(pathname, search, hash)
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

// The pages outside the console's frame, loaded on demand
function Loading() {
  return <Suspense fallback={<PageLoader />}><Outlet /></Suspense>
}

// A guide chapter the server drew is taken over with no Suspense boundary around it: React 18 leaves a
// boundary dehydrated after the first pass and draws it again at the first context update. The page is
// loaded before React takes over, so it never suspends.
function GuideRoute() {
  const page = <ProtectedRoute><GuidePage /></ProtectedRoute>
  return servedAtBoot() ? page : <Suspense fallback={<PageLoader />}>{page}</Suspense>
}

export function AppRoutes() {
  const { isAuthenticated, loading, sessionChecked, forcePasswordChange, clearForcePasswordChange, mustEnroll2fa, checkSession, logout } = useAuth()
  const { pathname } = useLocation()
  const gated = isAuthenticated && (mustEnroll2fa || forcePasswordChange)

  return (
    <>
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
        {/* The whole guide, read in a tab of its own: signed in, outside the console's frame */}
        <Route path="/guide" element={<GuideRoute />} />
        <Route path="/guide/:chapter" element={<GuideRoute />} />

        <Route element={<Loading />}>
          <Route
            path="/login"
            element={
              loading ? <PageLoader /> :
              isAuthenticated ? <SignedIn /> :
              <LoginPage />
            }
          />
          <Route
            path="/login/sso-complete"
            element={<LoginPage />}
          />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          {/* An SSO sign-in test's landing: no application shell, whoever signed in at the IdP */}
          <Route path="/sso-test-complete" element={<SsoTestCompletePage />} />
          <Route path="/sso-test-launch" element={<SsoTestLaunchPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />

          <Route element={<AppShell />}>
            {moduleRoutes()}
            {/* The Atelier gabarits: accessible by URL only, not a module */}
            {GabaritsPage && <Route path="/dev/gabarits" element={<ProtectedRoute><GabaritsPage /></ProtectedRoute>} />}
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>}
    </>
  )
}

// Router: BrowserRouter in the browser; the build draws the guide's chapters through a StaticRouter
export default function App({ Router = BrowserRouter, location }) {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <Router location={location}>
          <AuthProvider>
            <NotificationProvider>
            <WebSocketProvider>
              <MobileProvider>
                <InspectorProvider>
                  <SafeModeOverlay />
                  <AppRoutes />
                  <InspectorCloseOnNavigate />
                </InspectorProvider>
              </MobileProvider>
            </WebSocketProvider>
            </NotificationProvider>
          </AuthProvider>
        </Router>
      </ThemeProvider>
    </ErrorBoundary>
  )
}
