import React from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from '../Sidebar/Sidebar';
import TopBar from '../TopBar/TopBar';
import PreviewPanel from '../PreviewPanel/PreviewPanel';
import '../../../core/theme/layout.css';

const MainLayout = () => {
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#1a1a1a', color: '#e8e8e8' }}>
      <TopBar />
      <div className="main-layout" style={{ flex: 1 }}>
        <Sidebar />
        <div className="content-area">
          <Outlet />
        </div>
        <PreviewPanel />
      </div>
    </div>
  );
};

export default MainLayout;
