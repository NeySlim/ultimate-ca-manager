import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './components/layout/MainLayout/MainLayout';
import CertificatesPage from './modules/Certificates/pages/CertificatesPage';
import DashboardPage from './modules/Dashboard/pages/DashboardPage';
import SettingsPage from './modules/Settings/pages/SettingsPage';
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
        <Route path="certificates/*" element={<CertificatesPage />} />
        <Route path="cas/*" element={<div style={{padding: '20px'}}>Certificate Authorities Structure</div>} />
        <Route path="users" element={<div style={{padding: '20px'}}>Users Management</div>} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="analytics" element={<div style={{padding: '20px'}}>Analytics</div>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
