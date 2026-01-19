import React from 'react';
import { CaretLeft, CaretRight, House, SquaresFour, List, Rows, MagnifyingGlass, X } from '@phosphor-icons/react';
import { useView } from '../../../core/context/ViewContext';

const TopBar = () => {
  const { viewMode, setViewMode } = useView();

  return (
    <>
      {/* Topbar - macOS style */}
      <div className="topbar">
        <div className="nav-buttons">
          <button className="nav-btn"><CaretLeft weight="bold" /></button>
          <button className="nav-btn"><CaretRight weight="bold" /></button>
          <button className="nav-btn"><House weight="bold" /></button>
        </div>
        
        <div className="breadcrumb">
          <span className="breadcrumb-item">📜 Certificates</span>
          <span className="breadcrumb-sep">›</span>
          <span className="breadcrumb-item active">Active</span>
          <span className="breadcrumb-sep">›</span>
          <span className="breadcrumb-item active">Web Servers</span>
        </div>
        
        <div className="view-controls">
          <button 
            className={`view-btn ${viewMode === 'grid' ? 'active' : ''}`}
            onClick={() => setViewMode('grid')}
          >
            <SquaresFour weight="fill" />
          </button>
          <button 
            className={`view-btn ${viewMode === 'list' ? 'active' : ''}`}
            onClick={() => setViewMode('list')}
          >
            <List weight="bold" />
          </button>
          <button className="view-btn"><Rows weight="bold" /></button>
        </div>
        
        <div className="user-menu">👤 admin</div>
      </div>
      
      {/* Toolbar */}
      <div className="toolbar">
        <div className="search-box">
          <span className="icon"><MagnifyingGlass weight="bold" /></span>
          <input type="text" placeholder="Search certificates..." />
        </div>
        <div className="filter-tag">
          ⚡ Expiring Soon <span className="close"><X weight="bold" /></span>
        </div>
        <div className="filter-tag" style={{ background: '#2a2a2a', border: '1px solid #3a3a3a', color: '#ccc' }}>
          🔒 RSA Only <span className="close"><X weight="bold" /></span>
        </div>
      </div>
    </>
  );
};

export default TopBar;
