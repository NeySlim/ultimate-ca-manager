# UCM Frontend - Component Usage Examples

## Dashboard Grid Usage

### Basic Setup
```jsx
import DashboardGrid from './components/DashboardGrid';
import { StatWidget, ChartWidget } from './components/widgets';

export default function MyDashboard() {
  const [editMode, setEditMode] = useState(false);

  return (
    <DashboardGrid editMode={editMode} gap="16px">
      {/* Widgets go here */}
    </DashboardGrid>
  );
}
```

## Widget Examples

### StatWidget - Display Metrics
```jsx
import { StatWidget } from './components/widgets';
import { Folder, Calendar, X } from '@phosphor-icons/react';

// Simple stat
<div className="widget-1-3">
  <StatWidget
    icon={<Folder size={32} weight="duotone" />}
    value="1,248"
    label="Total Certificates"
    color="blue"
  />
</div>

// With trend
<div className="widget-1-3">
  <StatWidget
    icon={<Calendar size={32} weight="duotone" />}
    value="5"
    label="Expiring Soon"
    trend={{ value: 2, isPositive: false }}
    color="orange"
  />
</div>

// With positive trend
<div className="widget-1-3">
  <StatWidget
    icon={<X size={32} weight="duotone" />}
    value="2"
    label="Revoked"
    trend={{ value: 0, isPositive: true }}
    color="red"
  />
</div>
```

### ChartWidget - Visualize Data
```jsx
import { ChartWidget } from './components/widgets';

// With default mock data
<div className="widget-2-3">
  <ChartWidget 
    title="Certificates Issued (Last 6 Months)" 
  />
</div>

// With custom data
<div className="widget-2-3">
  <ChartWidget 
    title="Custom Chart"
    data={[
      { label: 'Jan', value: 40 },
      { label: 'Feb', value: 60 },
      { label: 'Mar', value: 50 },
      { label: 'Apr', value: 80 },
    ]}
  />
</div>
```

### LogWidget - Show Logs
```jsx
import { LogWidget } from './components/widgets';

// With default mock logs
<div className="widget-full">
  <LogWidget 
    title="Recent Logs" 
    maxHeight="300px"
  />
</div>

// With custom logs
<div className="widget-full">
  <LogWidget 
    title="System Logs"
    logs={[
      { 
        timestamp: '2024-01-15 10:45:23', 
        level: 'info', 
        message: 'System started' 
      },
      { 
        timestamp: '2024-01-15 10:44:12', 
        level: 'success', 
        message: 'Connection established' 
      },
    ]}
    maxHeight="250px"
  />
</div>
```

### ActivityWidget - Show Activities
```jsx
import { ActivityWidget } from './components/widgets';

// With default mock activities
<div className="widget-full">
  <ActivityWidget 
    title="Recent Activity" 
  />
</div>

// With custom activities
<div className="widget-full">
  <ActivityWidget 
    title="Custom Activities"
    activities={[
      { 
        id: 1, 
        type: 'issue', 
        user: 'admin', 
        action: 'Issued certificate', 
        subject: 'api.example.com', 
        timestamp: '5 mins ago', 
        icon: 'certificate' 
      },
      { 
        id: 2, 
        type: 'revoke', 
        user: 'user1', 
        action: 'Revoked certificate', 
        subject: 'old.example.com', 
        timestamp: '1 hour ago', 
        icon: 'user' 
      },
    ]}
  />
</div>
```

### StatusWidget - System Health
```jsx
import { StatusWidget } from './components/widgets';

// With default mock status
<div className="widget-1-3">
  <StatusWidget 
    title="System Status" 
  />
</div>

// With custom status
<div className="widget-1-3">
  <StatusWidget 
    title="Infrastructure Status"
    status={{
      overall: 'healthy', // healthy | warning | error
      components: [
        { 
          name: 'API Server', 
          status: 'healthy', 
          uptime: '99.99%', 
          responseTime: '45ms' 
        },
        { 
          name: 'Database', 
          status: 'warning', 
          uptime: '98.5%', 
          responseTime: '200ms' 
        },
      ]
    }}
  />
</div>
```

## Complete Dashboard Example

```jsx
import React, { useState } from 'react';
import { Pencil, ArrowClockwise, Folder, Calendar, X } from '@phosphor-icons/react';
import DashboardGrid from './components/DashboardGrid';
import {
  StatWidget,
  ChartWidget,
  LogWidget,
  ActivityWidget,
  StatusWidget
} from './components/widgets';
import './DashboardPage.css';

export default function CompleteDashboard() {
  const [editMode, setEditMode] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleRefresh = () => {
    setLoading(true);
    // Fetch fresh data here
    setTimeout(() => setLoading(false), 1000);
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
          >
            <Pencil size={16} weight={editMode ? 'fill' : 'regular'} />
            <span>{editMode ? 'Editing' : 'Edit'}</span>
          </button>

          <button 
            className="toolbar-btn"
            onClick={handleRefresh}
            disabled={loading}
          >
            <ArrowClockwise 
              size={16} 
              style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} 
            />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Dashboard Grid */}
      <DashboardGrid editMode={editMode}>
        {/* Row 1: Statistics */}
        <div className="widget-1-3">
          <StatWidget
            icon={<Folder size={32} weight="duotone" />}
            value="1,248"
            label="Total Certificates"
            trend={{ value: 12, isPositive: true }}
            color="blue"
          />
        </div>

        <div className="widget-1-3">
          <StatWidget
            icon={<Calendar size={32} weight="duotone" />}
            value="5"
            label="Expiring Soon"
            trend={{ value: 2, isPositive: false }}
            color="orange"
          />
        </div>

        <div className="widget-1-3">
          <StatWidget
            icon={<X size={32} weight="duotone" />}
            value="2"
            label="Revoked"
            color="red"
          />
        </div>

        {/* Row 2: Chart & Status */}
        <div className="widget-2-3">
          <ChartWidget 
            title="Certificates Issued (Last 6 Months)" 
          />
        </div>

        <div className="widget-1-3">
          <StatusWidget title="System Status" />
        </div>

        {/* Row 3: Activity */}
        <div className="widget-full">
          <ActivityWidget title="Recent Activity" />
        </div>

        {/* Row 4: Logs */}
        <div className="widget-full">
          <LogWidget 
            title="Recent Logs" 
            maxHeight="250px"
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
}
```

## Widget Size Reference

| Size Class | Width | Use Case |
|-----------|-------|----------|
| `widget-1-3` | 33% (4/12) | Small stats, single metrics |
| `widget-1-2` | 50% (6/12) | Medium widgets, small charts |
| `widget-2-3` | 66% (8/12) | Large charts, wide content |
| `widget-full` | 100% (12/12) | Tables, full-width content |

## Color Variants

All widgets support color props:
- `blue` - Primary, informational
- `green` - Success, positive
- `orange` - Warning, caution
- `red` - Error, critical

## Customization

### Custom Chart Data
```jsx
const chartData = [
  { label: 'Week 1', value: 100 },
  { label: 'Week 2', value: 150 },
  { label: 'Week 3', value: 120 },
  { label: 'Week 4', value: 200 },
];

<ChartWidget title="Custom Chart" data={chartData} />
```

### Custom Log Entries
```jsx
const customLogs = [
  { 
    timestamp: '2024-01-15 12:00:00', 
    level: 'error', 
    message: 'Connection failed' 
  },
  { 
    timestamp: '2024-01-15 11:59:00', 
    level: 'warning', 
    message: 'High latency detected' 
  },
];

<LogWidget logs={customLogs} />
```

### Custom Activities
```jsx
const customActivities = [
  {
    id: 1,
    type: 'issue', // issue | revoke | renew | export | update
    user: 'john_doe',
    action: 'Issued new certificate',
    subject: 'mail.example.com',
    timestamp: '5 minutes ago',
    icon: 'certificate'
  },
];

<ActivityWidget activities={customActivities} />
```

## CSS Customization

Override colors in your CSS:
```css
/* Dashboard grid gap */
.dashboard-grid {
  --grid-gap: 20px; /* Change gap between widgets */
}

/* Widget styling */
.stat-widget.blue .stat-icon {
  background-color: rgba(90, 143, 199, 0.1);
  color: #5a8fc7;
}

/* Chart colors */
.bar-fill {
  background: linear-gradient(180deg, #5a8fc7 0%, #4a7fb7 100%);
}
```

## Performance Tips

1. **Lazy Load Widgets** - Use React.lazy() for widgets not immediately visible
2. **Memoize Props** - Use useMemo() for computed trend values
3. **Pagination** - For large tables, use pagination instead of showing all rows
4. **Virtual Scrolling** - For logs with thousands of entries, consider virtualization

## Next Steps

1. Connect widgets to real API endpoints
2. Add auto-refresh intervals
3. Implement real-time data updates (WebSocket)
4. Add export functionality
5. Create custom widget templates
6. Implement dashboard state persistence
