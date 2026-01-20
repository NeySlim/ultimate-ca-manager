import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  Users, Certificate, ShieldCheck, HardDrives, Sliders
} from '@phosphor-icons/react';

const SidebarItem = ({ to, icon: Icon, label, end }) => (
  <NavLink 
    to={to} 
    end={end}
    className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`}
  >
    <Icon size={18} className="icon" />
    <span className="label">{label}</span>
  </NavLink>
);

const Sidebar = () => {
  return (
    <div className="sidebar">
      {/* SECTION 1: Favorites */}
      <div className="sidebar-section">
        <div className="sidebar-title">Favorites</div>
        <SidebarItem to="/users" label="Users" icon={Users} />
        <SidebarItem to="/certificates" label="Certificates" icon={Certificate} />
        <SidebarItem to="/cas" label="Authorities" icon={ShieldCheck} />
      </div>
      
      {/* SECTION 2: System */}
      <div className="sidebar-section">
        <div className="sidebar-title">System</div>
        <SidebarItem to="/backups" label="Backups" icon={HardDrives} />
        <SidebarItem to="/settings" label="Settings" icon={Sliders} />
      </div>
    </div>
  );
};

export default Sidebar;
