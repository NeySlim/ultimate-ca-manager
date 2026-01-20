import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './components/layout/MainLayout/MainLayout';
import CertificatesRoutes from './modules/Certificates/routes';
import DashboardPage from './modules/Dashboard/pages/DashboardPage';
import UserDetailPage from './modules/Users/pages/UserDetailPage';
import SettingsPage from './modules/Settings/pages/SettingsPage';
import AuditPage from './modules/Settings/pages/AuditPage';
import CATreePage from './modules/CAs/pages/CATreePage';
import CACreatePage from './modules/CAs/pages/CACreatePage';
import CADetailPage from './modules/CAs/pages/CADetailPage';
import CSRListPage from './modules/CSRs/pages/CSRListPage';
import ACMEPage from './modules/ACME/pages/ACMEPage';
import SCEPPage from './modules/SCEP/pages/SCEPPage';
import ValidationPage from './modules/Validation/pages/ValidationPage';
import UsersPage from './modules/Users/pages/UsersPage';
import LoginPage from './modules/Auth/pages/LoginPage';
import { RequireAuth } from './core/context/AuthContext';

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      
      <Route path="/" element={
        <RequireAuth>
          <MainLayout />
        </RequireAuth>
      }>
        <Route index element={<DashboardPage />} />
        <Route path="certificates/*" element={<CertificatesRoutes />} />
        <Route path="cas" element={<Navigate to="/cas/tree" replace />} />
        <Route path="cas/tree" element={<CATreePage />} />
        <Route path="cas/create" element={<CACreatePage />} />
        <Route path="cas/:id" element={<CADetailPage />} />
        <Route path="csrs" element={<CSRListPage />} />
        <Route path="acme" element={<ACMEPage />} />
        <Route path="scep" element={<SCEPPage />} />
        <Route path="validation" element={<ValidationPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="users/:id" element={<UserDetailPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="analytics" element={<div style={{padding: '20px'}}>Analytics</div>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
