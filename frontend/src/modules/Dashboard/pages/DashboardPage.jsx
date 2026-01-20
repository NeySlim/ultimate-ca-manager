import React, { useState } from 'react';
import { List, Pencil, ArrowClockwise, Folder, Calendar, X } from '@phosphor-icons/react';
import DashboardGrid from '../components/DashboardGrid';
import StatWidget from '../components/widgets/StatWidget';
import ChartWidget from '../components/widgets/ChartWidget';
import LogWidget from '../components/widgets/LogWidget';
import ActivityWidget from '../components/widgets/ActivityWidget';
import StatusWidget from '../components/widgets/StatusWidget';
import './DashboardPage.css';

const DashboardPage = () => {
  const [editMode, setEditMode] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleRefresh = () => {
    setLoading(true);
    // Simulate refresh
    setTimeout(() => {
      setLoading(false);
    }, 1000);
  };

  return (
    <div className="dashboard-page">
      {/* Toolbar */}
      <div className="dashboard-toolbar">
        <div className="toolbar-left">
          <h2 className="page-title">Dashboard</h2>
        </div>

        <div className="toolbar-actions">
          <button 
            className={`toolbar-btn ${editMode ? 'active' : ''}`}
            onClick={() => setEditMode(!editMode)}
            title={editMode ? 'Exit edit mode' : 'Enter edit mode'}
          >
            <Pencil size={16} weight={editMode ? 'fill' : 'regular'} />
            <span>{editMode ? 'Editing' : 'Edit'}</span>
          </button>

          <button 
            className="toolbar-btn"
            onClick={handleRefresh}
            disabled={loading}
            title="Refresh dashboard"
          >
            <ArrowClockwise size={16} weight="regular" style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Dashboard Grid with Widgets */}
      <DashboardGrid editMode={editMode}>
        {/* Top Row - Stats */}
        <div className="widget-1-3">
          <StatWidget
            icon={<Folder size={32} weight="duotone" className="icon-gradient-glow" />}
            value="1,248"
            label="Total Certificates"
            trend={{ value: 12, isPositive: true }}
            color="blue"
          />
        </div>

        <div className="widget-1-3">
          <StatWidget
            icon={<Calendar size={32} weight="duotone" className="icon-gradient-glow" />}
            value="5"
            label="Expiring Soon"
            trend={{ value: 2, isPositive: false }}
            color="orange"
          />
        </div>

        <div className="widget-1-3">
          <StatWidget
            icon={<X size={32} weight="duotone" className="icon-gradient-glow" />}
            value="2"
            label="Revoked"
            trend={{ value: 0, isPositive: true }}
            color="red"
          />
        </div>

        {/* Middle Row - Chart */}
        <div className="widget-2-3">
          <ChartWidget 
            title="Certificates Issued (Last 6 Months)" 
            size="widget-2-3"
          />
        </div>

        {/* Status Widget */}
        <div className="widget-1-3">
          <StatusWidget 
            title="System Status" 
            size="widget-1-3"
          />
        </div>

        {/* Activity Widget - Full Width */}
        <div className="widget-full">
          <ActivityWidget 
            title="Recent Activity" 
            size="widget-full"
          />
        </div>

        {/* Logs Widget - Full Width */}
        <div className="widget-full">
          <LogWidget 
            title="Recent Logs" 
            maxHeight="250px"
            size="widget-full"
          />
        </div>
      </DashboardGrid>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default DashboardPage;
