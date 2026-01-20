import React, { useState } from 'react';
import { ClockCounterClockwise, User, Certificate } from '@phosphor-icons/react';
import './ActivityWidget.css';

/**
 * ActivityWidget Component
 * 
 * Table of recent actions/activities
 * 
 * Props:
 *   - title: string - widget title
 *   - activities: array - activity entries
 *   - size: string - widget size class
 */
const ActivityWidget = ({ 
  title = 'Recent Activity', 
  activities = null,
  size = 'widget-full'
}) => {
  const [sortBy, setSortBy] = useState('time');

  // Mock activity data
  const mockActivities = [
    { id: 1, type: 'issue', user: 'admin', action: 'Issued new certificate', subject: 'mail.example.com', timestamp: '2 minutes ago', icon: 'certificate' },
    { id: 2, type: 'revoke', user: 'john.doe', action: 'Revoked certificate', subject: 'old.app.internal', timestamp: '15 minutes ago', icon: 'user' },
    { id: 3, type: 'renew', user: 'admin', action: 'Renewed certificate', subject: 'api.example.com', timestamp: '1 hour ago', icon: 'certificate' },
    { id: 4, type: 'export', user: 'jane.smith', action: 'Exported certificate', subject: 'vpn.gateway.lan', timestamp: '3 hours ago', icon: 'user' },
    { id: 5, type: 'update', user: 'admin', action: 'Updated CA settings', subject: 'Root CA', timestamp: 'Yesterday', icon: 'certificate' },
  ];

  const activityData = activities || mockActivities;

  const getActionColor = (type) => {
    switch (type) {
      case 'issue':
        return 'var(--mantine-color-green-6)';
      case 'revoke':
        return 'var(--mantine-color-red-6)';
      case 'renew':
        return 'var(--mantine-color-orange-6)';
      case 'export':
        return 'var(--mantine-color-blue-6)';
      case 'update':
        return 'var(--mantine-color-grape-6)';
      default:
        return 'var(--mantine-color-gray-6)';
    }
  };

  const getIcon = (type) => {
    switch (type) {
      case 'user':
        return <User size={14} weight="bold" />;
      case 'certificate':
      default:
        return <Certificate size={14} weight="bold" />;
    }
  };

  return (
    <div className={`activity-widget ${size}`}>
      <div className="activity-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ClockCounterClockwise size={16} weight="bold" />
          <h3 className="activity-title">{title}</h3>
        </div>
      </div>

      <div className="activity-table-wrapper">
        <table className="activity-table">
          <thead>
            <tr>
              <th style={{ width: '80px' }}>Type</th>
              <th>Action</th>
              <th style={{ width: '140px' }}>User</th>
              <th style={{ width: '180px' }}>Subject</th>
              <th style={{ width: '100px', textAlign: 'right' }}>Time</th>
            </tr>
          </thead>
          <tbody>
            {activityData.map((activity) => (
              <tr key={activity.id} className={`activity-row activity-${activity.type}`}>
                <td>
                  <div 
                    className="activity-badge"
                    style={{ 
                      backgroundColor: `${getActionColor(activity.type)}20`,
                      color: getActionColor(activity.type)
                    }}
                  >
                    {activity.type}
                  </div>
                </td>
                <td>
                  <div className="activity-action">{activity.action}</div>
                </td>
                <td>
                  <div className="activity-user">
                    <span className="user-icon">{getIcon('user')}</span>
                    {activity.user}
                  </div>
                </td>
                <td>
                  <div className="activity-subject">
                    <span className="subject-icon">{getIcon(activity.icon)}</span>
                    {activity.subject}
                  </div>
                </td>
                <td>
                  <div className="activity-time">{activity.timestamp}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="activity-footer">
        <a href="#" className="activity-link">View all activity →</a>
      </div>
    </div>
  );
};

export default ActivityWidget;
