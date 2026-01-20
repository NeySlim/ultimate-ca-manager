# UCM Frontend - Phase 1 Implementation Guide

## Overview

This document describes the Phase 1 implementation of the UCM (Ultimate Certificate Manager) Frontend. It includes dashboard components with widgets, a Grafana-style CSS Grid layout, and a comprehensive login page.

## Project Structure

```
src/
├── modules/
│   ├── Dashboard/
│   │   ├── components/
│   │   │   ├── DashboardGrid.jsx          # Main grid container
│   │   │   ├── DashboardGrid.css          # Grid styling
│   │   │   ├── index.js                   # Component exports
│   │   │   └── widgets/
│   │   │       ├── StatWidget.jsx         # Statistics widget
│   │   │       ├── ChartWidget.jsx        # Chart visualization
│   │   │       ├── LogWidget.jsx          # Log viewer
│   │   │       ├── ActivityWidget.jsx     # Activity table
│   │   │       ├── StatusWidget.jsx       # System status
│   │   │       ├── (individual CSS files)
│   │   │       └── index.js               # Widget exports
│   │   └── pages/
│   │       ├── DashboardPage.jsx          # Main dashboard page
│   │       └── DashboardPage.css          # Dashboard styling
│   └── Auth/
│       ├── pages/
│       │   └── LoginPage.jsx              # Login page (pre-existing)
│       └── auth.css                       # Login styling (pre-existing)
└── core/
    └── theme/
        ├── layout.css                     # Global layout styles
        ├── global.css                     # Global styles
        └── mantine.config.js              # Mantine theme config
```

## Components

### 1. DashboardGrid
**File:** `components/DashboardGrid.jsx` & `components/DashboardGrid.css`

The main container for dashboard widgets using CSS Grid.

**Features:**
- Responsive 12-column grid layout
- Support for multiple widget sizes:
  - `widget-1-3` - 1/3 width (4 columns)
  - `widget-1-2` - 1/2 width (6 columns)
  - `widget-2-3` - 2/3 width (8 columns)
  - `widget-full` - Full width (12 columns)
- Edit mode support with visual cues
- Mobile-responsive breakpoints (1200px, 768px, 480px)
- Grafana-style appearance with hover effects

**Usage:**
```jsx
<DashboardGrid editMode={true} gap="16px">
  <div className="widget-1-3">
    <StatWidget ... />
  </div>
  {/* more widgets */}
</DashboardGrid>
```

### 2. StatWidget
**File:** `components/widgets/StatWidget.jsx` & `StatWidget.css`

Displays key statistics with icons, values, labels, and trend indicators.

**Props:**
- `icon` - React component (e.g., `<Folder size={32} />`)
- `value` - Number or string to display
- `label` - Description label
- `trend` - Object with `{value: number, isPositive: boolean}`
- `color` - 'blue' | 'green' | 'orange' | 'red'
- `size` - Widget size class

**Example:**
```jsx
<StatWidget
  icon={<Folder size={32} weight="duotone" />}
  value="1,248"
  label="Total Certificates"
  trend={{ value: 12, isPositive: true }}
  color="blue"
/>
```

### 3. ChartWidget
**File:** `components/widgets/ChartWidget.jsx` & `ChartWidget.css`

Displays a bar chart visualization with CSS-based rendering.

**Props:**
- `title` - Chart title
- `data` - Array of `{label, value}` objects (uses mock data if not provided)
- `size` - Widget size class

**Features:**
- Mock data generation for demonstration
- Responsive bar heights based on data values
- Y-axis labels
- Hover effects on bars

### 4. LogWidget
**File:** `components/widgets/LogWidget.jsx` & `LogWidget.css`

Terminal-like log viewer with auto-scroll capability.

**Props:**
- `title` - Widget title
- `logs` - Array of `{timestamp, level, message}` objects
- `maxHeight` - CSS height value for scrollable area
- `size` - Widget size class

**Features:**
- Color-coded log levels (error, warning, success, info)
- Auto-scroll toggle
- Monospace font for log entries
- Smooth scrolling behavior
- Mock log data included

### 5. ActivityWidget
**File:** `components/widgets/ActivityWidget.jsx` & `ActivityWidget.css`

Table displaying recent system activities.

**Props:**
- `title` - Widget title
- `activities` - Array of activity objects with type, user, action, subject, timestamp
- `size` - Widget size class

**Features:**
- Sortable columns
- Color-coded activity types (issue, revoke, renew, export, update)
- User and subject icons
- Responsive table design
- Mock activity data included

### 6. StatusWidget
**File:** `components/widgets/StatusWidget.jsx` & `StatusWidget.css`

System health status overview with component status list.

**Props:**
- `title` - Widget title
- `status` - Object with `{overall, components[]}`
- `size` - Widget size class

**Features:**
- Overall status indicator (healthy, warning, error)
- Component-level status tracking
- Uptime and response time metrics
- Color-coded status badges
- Mock status data included

### 7. DashboardPage
**File:** `pages/DashboardPage.jsx` & `pages/DashboardPage.css`

Main dashboard page assembling all widgets and providing controls.

**Features:**
- Toolbar with Edit and Refresh buttons
- Edit mode toggle for widget layout editing
- Refresh functionality (with loading state)
- Pre-assembled dashboard layout with all widget types
- Responsive design

## Styling

### Theme Colors
The application uses a dark theme consistent with the Mantine theme:

```css
/* Primary Colors */
--accent-gradient-start: #5a8fc7;
--accent-gradient-end: #7aa5d9;

/* Background Colors */
--bg-primary: #1a1a1a;
--bg-secondary: #1e1e1e;
--bg-tertiary: #25262b;

/* Text Colors */
--text-primary: #e8e8e8;
--text-secondary: #c1c2c5;
--text-tertiary: #909296;

/* Status Colors */
--status-success: #81c784;
--status-warning: #ffb74d;
--status-error: #e57373;
--status-info: #64b5f6;
```

### CSS Grid Breakpoints

| Breakpoint | Columns | Target Device |
|------------|---------|---------------|
| > 1200px   | 12      | Desktop       |
| 768-1200px | 8       | Tablet        |
| 480-768px  | 6       | Small Tablet  |
| < 480px    | 1       | Mobile        |

## Widget Size Guide

Use widget size classes to control layout:

- **1/3 Width (4 cols):** StatWidget, small metrics
- **1/2 Width (6 cols):** Medium widgets, charts
- **2/3 Width (8 cols):** Wide charts, tables
- **Full Width (12 cols):** Logs, full activity tables, large content

## LoginPage

The LoginPage (`modules/Auth/pages/LoginPage.jsx`) is already implemented with:

- mTLS simulation (1-second check)
- Password-based authentication
- WebAuthn placeholder
- Integration with AuthContext
- Responsive design matching the dashboard theme
- Form validation and error handling

## Usage Example

```jsx
import { DashboardGrid, StatWidget, ChartWidget } from '../components';
import { Folder, Calendar } from '@phosphor-icons/react';

export default function Dashboard() {
  const [editMode, setEditMode] = useState(false);

  return (
    <DashboardGrid editMode={editMode}>
      <div className="widget-1-3">
        <StatWidget
          icon={<Folder size={32} weight="duotone" />}
          value="1,248"
          label="Total Items"
        />
      </div>
      
      <div className="widget-2-3">
        <ChartWidget title="Monthly Stats" />
      </div>
    </DashboardGrid>
  );
}
```

## Key Features

✅ **Responsive Design** - Works on desktop, tablet, and mobile
✅ **Dark Theme** - Consistent with Mantine dark theme
✅ **CSS Grid Layout** - Grafana-style widget positioning
✅ **Mock Data** - Included in widgets for demonstration
✅ **Edit Mode** - Visual indicators for widget editing
✅ **Performance** - Optimized CSS and component structure
✅ **Accessibility** - Semantic HTML and ARIA labels
✅ **Theming** - Uses Mantine components and custom CSS

## Build & Development

```bash
# Install dependencies
npm install

# Development server
npm run dev

# Production build
npm run build

# Preview production build
npm run preview
```

## Notes

- All widgets accept optional data props or use mock data by default
- Colors are customizable via the `color` prop on widgets
- Grid gaps can be adjusted via the `gap` prop on DashboardGrid
- Icons use `@phosphor-icons/react` for consistency
- All CSS uses CSS custom properties for easy theming

## Future Enhancements

- Real-time data integration
- Drag-and-drop widget reordering (edit mode)
- Widget resizing in edit mode
- Export dashboard as image/PDF
- Dashboard templates/presets
- Custom widget creation
- Data refresh intervals
- Widget configuration panels

## Build Status

✅ Build successful with all components compiled
✅ No TypeScript errors
✅ Responsive design tested
✅ Dark theme validated
✅ All imports resolved
