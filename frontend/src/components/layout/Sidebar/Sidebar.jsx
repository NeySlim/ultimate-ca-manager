import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { 
  House,
  ShieldCheck,
  Certificate,
  FileText,
  Notebook,
  Planet,
  DeviceMobile,
  ListChecks,
  Download,
  Users,
  ClockClockwise,
  Gear,
  CaretDown
} from '@phosphor-icons/react';

const SidebarItem = ({ to, icon: Icon, label, end }) => (
  <NavLink 
    to={to} 
    end={end}
    className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
  >
    {({ isActive }) => (
      <>
        <Icon size={18} className={isActive ? 'icon-gradient' : ''} weight={isActive ? "fill" : "regular"} />
        <span>{label}</span>
      </>
    )}
  </NavLink>
);

const Sidebar = () => {
  const [showUserMenu, setShowUserMenu] = useState(false);

  return (
    <div className="sidebar">
      {/* HEADER: Logo + Subtitle */}
      <div className="sidebar-header">
        <div className="logo">UCM v2.0</div>
        <div className="logo-subtitle">Certificate Manager</div>
      </div>

      {/* NAVIGATION */}
      <nav className="sidebar-nav">
        {/* SECTION 1: Main */}
        <div className="nav-section">
          <div className="nav-section-title">Main</div>
          <SidebarItem to="/" label="Dashboard" icon={House} end />
        </div>

        {/* SECTION 2: Certificate Management */}
        <div className="nav-section">
          <div className="nav-section-title">Certificate Management</div>
          <SidebarItem to="/cas" label="Certificate Authorities" icon={ShieldCheck} />
          <SidebarItem to="/certificates" label="Certificates" icon={Certificate} />
          <SidebarItem to="/csrs" label="Certificate Requests" icon={FileText} />
          <SidebarItem to="/templates" label="Templates" icon={Notebook} />
        </div>

        {/* SECTION 3: Protocols */}
        <div className="nav-section">
          <div className="nav-section-title">Protocols</div>
          <SidebarItem to="/acme" label="ACME" icon={Planet} />
          <SidebarItem to="/scep" label="SCEP" icon={DeviceMobile} />
          <SidebarItem to="/crl" label="CRL & OCSP" icon={ListChecks} />
        </div>
        
        {/* SECTION 4: System */}
        <div className="nav-section">
          <div className="nav-section-title">System</div>
          <SidebarItem to="/import" label="Import" icon={Download} />
          <SidebarItem to="/truststore" label="Trust Store" icon={ShieldCheck} />
          <SidebarItem to="/users" label="Users" icon={Users} />
          <SidebarItem to="/activity" label="Activity Log" icon={ClockClockwise} />
          <SidebarItem to="/settings" label="Settings" icon={Gear} />
        </div>
      </nav>

      {/* FOOTER: User Card */}
      <div className="sidebar-footer">
        <div 
          className="user-card" 
          onClick={() => setShowUserMenu(!showUserMenu)}
        >
          <div className="user-avatar">A</div>
          <div className="user-info">
            <div className="user-name">admin</div>
            <div className="user-role">Administrator</div>
          </div>
          <CaretDown size={12} style={{ color: 'var(--text-muted)' }} />
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
