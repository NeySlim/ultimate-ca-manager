import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  House, Users, Certificate, ShieldCheck, Sliders, FileText, Globe, Devices
} from '@phosphor-icons/react';

const SidebarItem = ({ to, icon: Icon, label, end }) => (
  <NavLink 
    to={to} 
    end={end}
    className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`}
  >
    {({ isActive }) => (
      <>
        <Icon size={18} className={`icon ${isActive ? 'icon-gradient' : ''}`} weight={isActive ? "fill" : "regular"} />
        <span className="label">{label}</span>
      </>
    )}
  </NavLink>
);

const Sidebar = () => {
  return (
    <div className="sidebar">
      {/* SECTION 1: Overview */}
      <div className="sidebar-section">
        <SidebarItem to="/" label="Dashboard" icon={House} end />
      </div>

      {/* SECTION 2: PKI Management */}
      <div className="sidebar-section">
        <div className="sidebar-title">PKI Management</div>
        <SidebarItem to="/cas" label="Authorities" icon={ShieldCheck} />
        <SidebarItem to="/certificates" label="Certificates" icon={Certificate} />
        <SidebarItem to="/csrs" label="CSRs" icon={FileText} />
      </div>

      {/* SECTION 3: Services */}
      <div className="sidebar-section">
        <div className="sidebar-title">Services</div>
        <SidebarItem to="/acme" label="ACME Protocol" icon={Globe} />
        <SidebarItem to="/scep" label="SCEP Server" icon={Devices} />
      </div>
      
      {/* SECTION 4: System */}
      <div className="sidebar-section">
        <div className="sidebar-title">System</div>
        <SidebarItem to="/users" label="Users" icon={Users} />
        <SidebarItem to="/settings" label="Settings" icon={Sliders} />
      </div>
    </div>
  );
};

export default Sidebar;
