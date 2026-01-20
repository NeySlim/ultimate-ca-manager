import React from 'react';
import { CheckCircle, Warning, Pulse } from '@phosphor-icons/react';
import './StatusWidget.css';

/**
 * StatusWidget Component
 * 
 * System status health check display
 * 
 * Props:
 *   - title: string - widget title
 *   - status: object - status data with components
 *   - size: string - widget size class
 */
const StatusWidget = ({ 
  title = 'System Status', 
  status = null,
  size = 'widget-1-2'
}) => {
  // Mock status data
  const mockStatus = {
    overall: 'healthy', // healthy | warning | error
    components: [
      { name: 'API Server', status: 'healthy', uptime: '99.99%', responseTime: '45ms' },
      { name: 'Database', status: 'healthy', uptime: '100%', responseTime: '12ms' },
      { name: 'Certificate Store', status: 'healthy', uptime: '99.95%', responseTime: '78ms' },
      { name: 'Backup Service', status: 'warning', uptime: '98.5%', responseTime: '1.2s' },
      { name: 'Cache Server', status: 'healthy', uptime: '99.8%', responseTime: '5ms' },
    ]
  };

  const statusData = status || mockStatus;

  const getStatusIcon = (componentStatus) => {
    switch (componentStatus) {
      case 'error':
        return { icon: '●', statusClass: 'status-error', label: 'Error' };
      case 'warning':
        return { icon: '●', statusClass: 'status-warning', label: 'Warning' };
      case 'healthy':
      default:
        return { icon: '●', statusClass: 'status-healthy', label: 'Healthy' };
    }
  };

  const getOverallStatus = () => {
    switch (statusData.overall) {
      case 'error':
        return { icon: '✗', statusClass: 'status-error', label: 'Critical' };
      case 'warning':
        return { icon: '⚠', statusClass: 'status-warning', label: 'Warning' };
      case 'healthy':
      default:
        return { icon: '✓', statusClass: 'status-healthy', label: 'Healthy' };
    }
  };

  const overall = getOverallStatus();

  return (
    <div className={`status-widget ${size}`}>
      <div className="status-header">
        <h3 className="status-title">{title}</h3>
      </div>

      {/* Overall Status Card */}
      <div className={`status-overall ${overall.statusClass}`}>
        <div className="overall-icon">
          <Pulse size={24} weight="bold" />
        </div>
        <div className="overall-content">
          <div className="overall-label">Overall Status</div>
          <div className="overall-value">
            {overall.label}
          </div>
        </div>
      </div>

      {/* Components Status List */}
      <div className="status-components">
        {statusData.components.map((component, index) => {
          const compStatus = getStatusIcon(component.status);
          return (
            <div key={index} className="status-component">
              <div className="component-info">
                <div className={`component-status-dot ${compStatus.statusClass}`}>
                  {compStatus.icon}
                </div>
                <div className="component-details">
                  <div className="component-name">{component.name}</div>
                  <div className="component-metrics">
                    <span>↑ {component.uptime}</span>
                    <span>⚡ {component.responseTime}</span>
                  </div>
                </div>
              </div>
              <div className={`component-badge ${compStatus.statusClass}`}>
                {compStatus.label}
              </div>
            </div>
          );
        })}
      </div>

      <div className="status-footer">
        <small>Last checked: Just now</small>
      </div>
    </div>
  );
};

export default StatusWidget;
