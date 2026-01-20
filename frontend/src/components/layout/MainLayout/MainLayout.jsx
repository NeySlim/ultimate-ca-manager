import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from '../Sidebar/Sidebar';
import TopBar from '../TopBar/TopBar';
import PreviewPanel from '../PreviewPanel/PreviewPanel';
import { ThemeSettings } from '../../ThemeSettings';
import '../../../core/theme/layout.css';

const MainLayout = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isDetailsOpen, setIsDetailsOpen] = useState(true);
  const [isThemeSettingsOpen, setIsThemeSettingsOpen] = useState(false);

  return (
    <div className="app-shell">
      {/* 1. Technical TopBar (48px) */}
      <TopBar 
        isSidebarOpen={isSidebarOpen} 
        toggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        isDetailsOpen={isDetailsOpen}
        toggleDetails={() => setIsDetailsOpen(!isDetailsOpen)}
        openThemeSettings={() => setIsThemeSettingsOpen(true)}
      />
      
      <ThemeSettings opened={isThemeSettingsOpen} onClose={() => setIsThemeSettingsOpen(false)} />

      <div className="layout-body">
        {/* 2. Sidebar (Collapsible) */}
        {isSidebarOpen && <Sidebar />}
        
        {/* 3. Main Content (Dashboard Grid) */}
        <div className="main-content">
          <Outlet />
        </div>
        
        {/* 4. Details Panel (Collapsible) */}
        {isDetailsOpen && <PreviewPanel />}
      </div>

      {/* 5. Status Bar (Footer 28px) */}
      <footer className="status-bar">
        <div className="status-left">
           <div className="status-item" title="Connection Status">
               <div className="status-dot online"></div>
               <span>Connected</span>
           </div>
           <div className="status-divider"></div>
           <div className="status-item">ucm-core:8000</div>
        </div>
        <div className="status-right">
           <div className="status-item">All Systems Operational</div>
           <div className="status-divider"></div>
           <div className="status-item">12ms</div>
           <div className="status-divider"></div>
           <div className="status-item">v2.0.0-rc1</div>
        </div>
      </footer>
    </div>
  );
};

export default MainLayout;
