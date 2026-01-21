import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router';
import { AppLayout } from '../components/layout/AppLayout';
import { ErrorBoundary } from '../components/ErrorBoundary';

// Lazy load pages for code splitting
const Login = lazy(() => import('../pages/Login'));
const Dashboard = lazy(() => import('../pages/Dashboard'));
const ActivityLog = lazy(() => import('../pages/activity/ActivityLog'));
const CAList = lazy(() => import('../pages/cas/CAList'));
const CertificateList = lazy(() => import('../pages/certificates/CertificateList'));
const CSRList = lazy(() => import('../pages/csrs/CSRList'));
const TemplateList = lazy(() => import('../pages/templates/TemplateList'));
const CRLManagement = lazy(() => import('../pages/crl/CRLManagement'));
const ACMEDashboard = lazy(() => import('../pages/acme/ACMEDashboard'));
const SCEPDashboard = lazy(() => import('../pages/scep/SCEPDashboard'));
const ImportPage = lazy(() => import('../pages/import/ImportPage'));
const TrustStore = lazy(() => import('../pages/truststore/TrustStore'));
const UserList = lazy(() => import('../pages/users/UserList'));
const Settings = lazy(() => import('../pages/settings/Settings'));
const Profile = lazy(() => import('../pages/profile/Profile'));

// Loading fallback component
function PageLoader() {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      height: '400px',
      color: 'var(--text-tertiary)',
    }}>
      <div style={{ textAlign: 'center' }}>
        <i className="ph ph-spinner" style={{ fontSize: '32px', marginBottom: '8px' }} />
        <div>Loading...</div>
      </div>
    </div>
  );
}

// Wrapper for lazy-loaded pages
function LazyPage({ children }) {
  return (
    <Suspense fallback={<PageLoader />}>
      {children}
    </Suspense>
  );
}

const router = createBrowserRouter([
  {
    path: '/login',
    element: <LazyPage><Login /></LazyPage>,
    errorElement: <ErrorBoundary />,
  },
  {
    path: '/',
    element: <AppLayout />,
    errorElement: <ErrorBoundary />,
    children: [
      {
        index: true,
        element: <Navigate to="/dashboard" replace />,
      },
      {
        path: 'dashboard',
        element: <LazyPage><Dashboard /></LazyPage>,
      },
      {
        path: 'activity',
        element: <LazyPage><ActivityLog /></LazyPage>,
      },
      {
        path: 'cas',
        element: <LazyPage><CAList /></LazyPage>,
      },
      {
        path: 'certificates',
        element: <LazyPage><CertificateList /></LazyPage>,
      },
      {
        path: 'csrs',
        element: <LazyPage><CSRList /></LazyPage>,
      },
      {
        path: 'templates',
        element: <LazyPage><TemplateList /></LazyPage>,
      },
      {
        path: 'crl',
        element: <LazyPage><CRLManagement /></LazyPage>,
      },
      {
        path: 'acme',
        element: <LazyPage><ACMEDashboard /></LazyPage>,
      },
      {
        path: 'scep',
        element: <LazyPage><SCEPDashboard /></LazyPage>,
      },
      {
        path: 'import',
        element: <LazyPage><ImportPage /></LazyPage>,
      },
      {
        path: 'truststore',
        element: <LazyPage><TrustStore /></LazyPage>,
      },
      {
        path: 'users',
        element: <LazyPage><UserList /></LazyPage>,
      },
      {
        path: 'settings',
        element: <LazyPage><Settings /></LazyPage>,
      },
      {
        path: 'profile',
        element: <LazyPage><Profile /></LazyPage>,
      },
    ],
  },
]);

export function AppRoutes() {
  return <RouterProvider router={router} />;
}

export default AppRoutes;
