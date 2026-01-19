import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  Star, Tray, CheckCircle, Warning, Prohibit, 
  LockKey, LockKeyOpen, Users, Gear, ChartBar 
} from '@phosphor-icons/react';

const SidebarItem = ({ to, icon: Icon, label, count, end }) => (
  <NavLink 
    to={to} 
    end={end}
    className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`}
  >
    <span className="icon"><Icon weight="fill" /></span>
    <span className="label">{label}</span>
    {count !== undefined && <span className="count">{count}</span>}
  </NavLink>
);

const Sidebar = () => {
  return (
    <div className="sidebar">
      <div className="sidebar-section">
        <div className="sidebar-title">Favorites</div>
        <SidebarItem to="/" label="Recent" icon={Star} end />
        <SidebarItem to="/certificates" label="All Certificates" icon={Tray} count={24} />
        <SidebarItem to="/certificates/valid" label="Valid" icon={CheckCircle} count={20} />
        <SidebarItem to="/certificates/expiring" label="Expiring" icon={Warning} count={2} />
        <SidebarItem to="/certificates/revoked" label="Revoked" icon={Prohibit} count={1} />
      </div>
      
      <div className="sidebar-section">
        <div className="sidebar-title">Certificate Authorities</div>
        <SidebarItem to="/cas/root" label="Root CA" icon={LockKey} count={1} />
        <SidebarItem to="/cas/intermediate" label="Intermediate" icon={LockKeyOpen} count={2} />
      </div>
      
      <div className="sidebar-section">
        <div className="sidebar-title">Management</div>
        <SidebarItem to="/users" label="Users" icon={Users} count={5} />
        <SidebarItem to="/settings" label="Settings" icon={Gear} />
        <SidebarItem to="/analytics" label="Analytics" icon={ChartBar} />
      </div>
    </div>
  );
};

export default Sidebar;
