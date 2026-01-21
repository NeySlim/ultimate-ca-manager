import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './components/layout/MainLayout/MainLayout';
import LoginPage from './modules/Auth/pages/LoginPage';
import DashboardPage from './modules/Dashboard/pages/DashboardPage';
import CAListPage from './modules/CAs/pages/CAListPage';
import CertificateListPage from './modules/Certificates/pages/CertificateListPage';
import CSRListPage from './modules/CSRs/pages/CSRListPage';
import ACMEPage from './modules/ACME/pages/ACMEPage';
import SCEPPage from './modules/SCEP/pages/SCEPPage';
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
        <Route path="cas" element={<CAListPage />} />
        <Route path="certificates" element={<CertificateListPage />} />
        <Route path="csrs" element={<CSRListPage />} />
        <Route path="acme" element={<ACMEPage />} />
        <Route path="scep" element={<SCEPPage />} />
        
        {/* Placeholder routes */}
        <Route path="users" element={<div className="page-container"><h1>Users - Coming Soon</h1></div>} />
        <Route path="settings" element={<div className="page-container"><h1>Settings - Coming Soon</h1></div>} />
        
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
