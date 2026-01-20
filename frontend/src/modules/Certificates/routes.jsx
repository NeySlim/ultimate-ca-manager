import React from 'react';
import { Routes, Route } from 'react-router-dom';
import CertificatesListPage from './pages/CertificatesListPage';
import CertificateDetailPage from './pages/CertificateDetailPage';

const CertificatesRoutes = () => {
  return (
    <Routes>
      <Route index element={<CertificatesListPage />} />
      <Route path=":id" element={<CertificateDetailPage />} />
    </Routes>
  );
};

export default CertificatesRoutes;
