import React from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  SidebarSimple, 
  House, 
  MagnifyingGlass, 
  Moon, 
  Sun,
  Bell, 
  Gear, 
  CaretDown,
  ListDashes,
  Rows,
  PencilSimple
} from '@phosphor-icons/react';
import { useTheme } from '../../../contexts/ThemeContext';
import LogoIcon from '../../../assets/logo-chain-icon.svg';

const TopBar = ({ isSidebarOpen, toggleSidebar, isDetailsOpen, toggleDetails, openThemeSettings }) => {
  const { density, setDensity, colorScheme, setColorScheme } = useTheme();
  const navigate = useNavigate();

  const toggleColorScheme = () => {
    setColorScheme(colorScheme === 'dark' ? 'light' : 'dark');
  };

  return (
    <div className="topbar">
      
      {/* 1. LEFT: Logo + Nav */}
      <div className="actions-group" style={{ marginRight: 'auto' }}>
        {/* Logo */}
        <div 
          onClick={() => navigate('/')}
          style={{ 
            display: 'flex', alignItems: 'center', gap: '8px', 
            fontWeight: 700, fontSize: '14px', color: 'var(--text-primary)', 
            paddingRight: '12px', borderRight: '1px solid var(--border-color)',
            cursor: 'pointer'
          }}
        >
          <img src={LogoIcon} alt="UCM Logo" style={{ width: '20px', height: '20px' }} />
          UCM
        </div>

        {/* Sidebar Toggle */}
        <button 
          className="nav-btn"
          onClick={toggleSidebar}
          title="Toggle Sidebar"
        >
          <SidebarSimple weight={isSidebarOpen ? "fill" : "regular"} />
        </button>

        {/* Breadcrumbs */}
        <div className="breadcrumb">
           <div 
             className="breadcrumb-item" 
             onClick={() => navigate('/')}
           >
             <House size={14} /> Home
           </div>
           <span className="breadcrumb-sep">/</span>
           <div className="breadcrumb-item active">Dashboard</div>
        </div>
      </div>

      {/* 2. CENTER: Command Palette */}
      <div style={{ flex: 1, display: 'flex', justifyContent: 'center', padding: '0 20px' }}>
         <div className="command-palette">
            <MagnifyingGlass size={14} />
            <input 
              type="text" 
              placeholder="Search resources..." 
            />
            <span className="command-shortcut">Ctrl+K</span>
         </div>
      </div>

      {/* 3. RIGHT: Actions */}
      <div className="actions-group" style={{ marginLeft: 'auto' }}>
        
        {/* View Toggles (Density) */}
        <div className="view-toggle-group">
           <button 
             className={`view-toggle-btn ${density === 'normal' ? 'active' : ''}`}
             onClick={() => setDensity('normal')}
             title="Normal Density"
           >
             <Rows size={16} />
           </button>
           <button 
             className={`view-toggle-btn ${density === 'compact' ? 'active' : ''}`}
             onClick={() => setDensity('compact')}
             title="Compact Density"
           >
             <ListDashes size={16} />
           </button>
        </div>

        {/* Layout Edit */}
        <button className="btn" style={{ height: 'var(--control-height)', fontSize: 'var(--font-size-control)' }}>
            <PencilSimple size={14} /> Edit Layout
        </button>

        <div style={{ width: '1px', height: '20px', backgroundColor: 'var(--border-color)' }}></div>

        <button className="action-btn" onClick={toggleDetails} title="Toggle Details">
           <SidebarSimple weight={isDetailsOpen ? "fill" : "regular"} style={{ transform: 'rotate(180deg)' }} />
        </button>
        
        <button className="action-btn" onClick={toggleColorScheme} title="Toggle Theme">
           {colorScheme === 'dark' ? <Moon weight="fill" /> : <Sun weight="fill" />}
        </button>

        <button className="action-btn">
           <Bell />
        </button>

        <button className="action-btn" onClick={openThemeSettings}>
           <Gear />
        </button>

        <div style={{ width: '1px', height: '20px', backgroundColor: 'var(--border-color)' }}></div>

        {/* User Profile */}
        <div className="user-menu">
           <div className="user-avatar">AD</div>
           <div className="user-name">Admin</div>
           <CaretDown size={12} color="var(--text-secondary)" />
        </div>

      </div>
    </div>
  );
};

export default TopBar;
