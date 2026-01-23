import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router';
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

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LazyPage><Login /></LazyPage>} />
      <Route path="/" element={<AppLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<LazyPage><Dashboard /></LazyPage>} />
        <Route path="activity" element={<LazyPage><ActivityLog /></LazyPage>} />
        <Route path="cas" element={<LazyPage><CAList /></LazyPage>} />
        <Route path="certificates" element={<LazyPage><CertificateList /></LazyPage>} />
        <Route path="csrs" element={<LazyPage><CSRList /></LazyPage>} />
        <Route path="templates" element={<LazyPage><TemplateList /></LazyPage>} />
        <Route path="crl" element={<LazyPage><CRLManagement /></LazyPage>} />
        <Route path="acme" element={<LazyPage><ACMEDashboard /></LazyPage>} />
        <Route path="scep" element={<LazyPage><SCEPDashboard /></LazyPage>} />
        <Route path="import" element={<LazyPage><ImportPage /></LazyPage>} />
        <Route path="truststore" element={<LazyPage><TrustStore /></LazyPage>} />
        <Route path="users" element={<LazyPage><UserList /></LazyPage>} />
        <Route path="settings" element={<LazyPage><Settings /></LazyPage>} />
        <Route path="profile" element={<LazyPage><Profile /></LazyPage>} />
      </Route>
    </Routes>
  );
}

export default AppRoutes;
