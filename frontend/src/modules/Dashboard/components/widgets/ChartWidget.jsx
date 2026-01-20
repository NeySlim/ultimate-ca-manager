import React from 'react';
import './ChartWidget.css';

/**
 * ChartWidget Component
 * 
 * Visual placeholder for charts. Currently displays a CSS-based bar chart mockup.
 * 
 * Props:
 *   - title: string - widget title
 *   - data: array - chart data (optional for mockup)
 *   - size: string - widget size class ('widget-1-2', 'widget-2-3', etc.)
 */
const ChartWidget = ({ 
  title = 'Chart', 
  data = null,
  size = 'widget-2-3' 
}) => {
  // Mock data for visual demonstration
  const mockData = [
    { label: 'Jan', value: 65 },
    { label: 'Feb', value: 78 },
    { label: 'Mar', value: 45 },
    { label: 'Apr', value: 82 },
    { label: 'May', value: 72 },
    { label: 'Jun', value: 91 },
  ];

  const chartData = data || mockData;
  const maxValue = Math.max(...chartData.map(d => d.value));

  return (
    <div className={`chart-widget ${size}`}>
      <div className="chart-header">
        <h3 className="chart-title">{title}</h3>
        <div className="chart-legend">
          <span className="legend-item">
            <span className="legend-color" style={{ backgroundColor: '#5a8fc7' }}></span>
            Total
          </span>
        </div>
      </div>
      
      <div className="chart-container">
        <div className="bars-container">
          {chartData.map((item, index) => (
            <div key={index} className="bar-wrapper">
              <div className="bar-label">{item.label}</div>
              <div className="bar">
                <div 
                  className="bar-fill" 
                  style={{ height: `${(item.value / maxValue) * 100}%` }}
                ></div>
              </div>
              <div className="bar-value">{item.value}</div>
            </div>
          ))}
        </div>
        
        <div className="y-axis">
          <div className="y-label">{maxValue}</div>
          <div className="y-label">{Math.round(maxValue * 0.75)}</div>
          <div className="y-label">{Math.round(maxValue * 0.5)}</div>
          <div className="y-label">{Math.round(maxValue * 0.25)}</div>
          <div className="y-label">0</div>
        </div>
      </div>
    </div>
  );
};

export default ChartWidget;
