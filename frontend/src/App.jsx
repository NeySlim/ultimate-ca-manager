import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import CAs from './pages/CAs'
import Certificates from './pages/Certificates'
import CSRs from './pages/CSRs'
import Settings from './pages/Settings'
import Users from './pages/Users'
import ACME from './pages/ACME'
import CRL from './pages/CRL'
import SCEP from './pages/SCEP'
import Templates from './pages/Templates'
import TrustStore from './pages/TrustStore'
import Account from './pages/Account'
import AppShell from './components/AppShell'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<AppShell />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="cas" element={<CAs />} />
          <Route path="certificates" element={<Certificates />} />
          <Route path="csrs" element={<CSRs />} />
          <Route path="settings" element={<Settings />} />
          <Route path="users" element={<Users />} />
          <Route path="acme" element={<ACME />} />
          <Route path="crl" element={<CRL />} />
          <Route path="scep" element={<SCEP />} />
          <Route path="templates" element={<Templates />} />
          <Route path="truststore" element={<TrustStore />} />
          <Route path="account" element={<Account />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
