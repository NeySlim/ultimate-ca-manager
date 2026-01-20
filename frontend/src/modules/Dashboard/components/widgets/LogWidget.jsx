import React, { useState, useEffect, useRef } from 'react';
import { Scroll } from '@phosphor-icons/react';
import './LogWidget.css';

/**
 * LogWidget Component
 * 
 * Terminal-like view for displaying log entries
 * 
 * Props:
 *   - title: string - widget title
 *   - logs: array - log entries
 *   - maxHeight: string - max height for scrollable area
 *   - size: string - widget size class
 */
const LogWidget = ({ 
  title = 'Recent Logs', 
  logs = null,
  maxHeight = '300px',
  size = 'widget-full'
}) => {
  const [autoScroll, setAutoScroll] = useState(true);
  const logsEndRef = useRef(null);

  // Mock log data
  const mockLogs = [
    { timestamp: '2024-01-15 10:45:23', level: 'info', message: 'Certificate renewal scheduled' },
    { timestamp: '2024-01-15 10:44:12', level: 'success', message: 'Successfully revoked certificate for example.com' },
    { timestamp: '2024-01-15 10:42:58', level: 'warning', message: 'Certificate api.example.com expiring in 30 days' },
    { timestamp: '2024-01-15 10:41:35', level: 'info', message: 'Backup completed successfully' },
    { timestamp: '2024-01-15 10:39:22', level: 'error', message: 'Failed to connect to certificate store' },
    { timestamp: '2024-01-15 10:38:10', level: 'info', message: 'Certificate validation passed' },
    { timestamp: '2024-01-15 10:35:45', level: 'success', message: 'New certificate issued for admin.internal' },
    { timestamp: '2024-01-15 10:33:20', level: 'warning', message: 'High memory usage detected' },
  ];

  const logData = logs || mockLogs;

  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logData, autoScroll]);

  const handleScroll = (e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.target;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    setAutoScroll(isAtBottom);
  };

  const getLevelColor = (level) => {
    switch (level) {
      case 'error':
        return 'var(--mantine-color-red-6)';
      case 'warning':
        return 'var(--mantine-color-orange-6)';
      case 'success':
        return 'var(--mantine-color-green-6)';
      case 'info':
      default:
        return 'var(--mantine-color-blue-6)';
    }
  };

  return (
    <div className={`log-widget ${size}`}>
      <div className="log-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Scroll size={16} weight="bold" />
          <h3 className="log-title">{title}</h3>
        </div>
        <div className="log-info">
          {logData.length} entries
        </div>
      </div>

      <div 
        className="log-container" 
        style={{ maxHeight }}
        onScroll={handleScroll}
      >
        {logData.map((log, index) => (
          <div key={index} className="log-entry">
            <div className="log-timestamp">{log.timestamp}</div>
            <div 
              className="log-level" 
              style={{ 
                backgroundColor: `${getLevelColor(log.level)}20`,
                color: getLevelColor(log.level)
              }}
            >
              {log.level.toUpperCase()}
            </div>
            <div className="log-message">{log.message}</div>
          </div>
        ))}
        <div ref={logsEndRef} />
      </div>

      <div className="log-footer">
        <label className="log-autoscroll">
          <input 
            type="checkbox" 
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
          />
          <span>Auto-scroll</span>
        </label>
      </div>
    </div>
  );
};

export default LogWidget;
