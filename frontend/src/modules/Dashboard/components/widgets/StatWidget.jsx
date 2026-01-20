import React from 'react';
import { ArrowUp, ArrowDown } from '@phosphor-icons/react';
import './StatWidget.css';

/**
 * StatWidget Component
 * 
 * Displays a statistic with icon, value, label, and trend indicator
 * 
 * Props:
 *   - icon: React component or element
 *   - value: string or number - main stat value
 *   - label: string - description of the stat
 *   - trend: { value: number, isPositive: boolean } - optional trend data
 *   - color: string - accent color for the stat ('green', 'orange', 'red', 'blue')
 *   - size: string - widget size class ('widget-1-3', 'widget-1-2', etc.)
 */
const StatWidget = ({ 
  icon, 
  value, 
  label, 
  trend = null, 
  color = 'blue',
  size = 'widget-1-3'
}) => {
  return (
    <div className={`stat-widget ${color} ${size}`}>
      <div className="stat-icon">
        {icon}
      </div>
      
      <div className="stat-content">
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
        
        {trend && (
          <div className={`stat-trend ${trend.isPositive ? 'positive' : 'negative'}`}>
            {trend.isPositive ? <ArrowUp size={14} weight="bold" /> : <ArrowDown size={14} weight="bold" />}
            <span>{Math.abs(trend.value)}%</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default StatWidget;
