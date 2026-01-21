import { Routes, Route } from 'react-router-dom';
import AppLayout from '../components/layout/AppLayout';

// Pages
import Dashboard from '../pages/Dashboard';
import CAList from '../pages/cas/CAList';
import CertificateList from '../pages/certificates/CertificateList';
import CSRList from '../pages/csrs/CSRList';
import TemplateList from '../pages/templates/TemplateList';
import CRLManagement from '../pages/crl/CRLManagement';
import ACMEDashboard from '../pages/acme/ACMEDashboard';
import SCEPDashboard from '../pages/scep/SCEPDashboard';
import ImportPage from '../pages/import/ImportPage';
import TrustStore from '../pages/truststore/TrustStore';
import UserList from '../pages/users/UserList';
import ActivityLog from '../pages/activity/ActivityLog';
import Settings from '../pages/settings/Settings';
import Profile from '../pages/profile/Profile';

/**
 * Application Routes
 * 
 * All routes wrapped in AppLayout (Sidebar + Topbar)
 * 14 main pages from prototype suite
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AppLayout />}>
        {/* Main */}
        <Route index element={<Dashboard />} />
        
        {/* Certificate Management */}
        <Route path="cas" element={<CAList />} />
        <Route path="certificates" element={<CertificateList />} />
        <Route path="csrs" element={<CSRList />} />
        <Route path="templates" element={<TemplateList />} />
        <Route path="crl" element={<CRLManagement />} />
        
        {/* Protocols */}
        <Route path="acme" element={<ACMEDashboard />} />
        <Route path="scep" element={<SCEPDashboard />} />
        
        {/* System */}
        <Route path="import" element={<ImportPage />} />
        <Route path="truststore" element={<TrustStore />} />
        <Route path="users" element={<UserList />} />
        <Route path="activity" element={<ActivityLog />} />
        <Route path="settings" element={<Settings />} />
        <Route path="profile" element={<Profile />} />
      </Route>
    </Routes>
  );
}

export default AppRoutes;
