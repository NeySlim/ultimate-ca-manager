/**
 * Dashboard Grid Layout Configuration
 * 
 * Grid system: 12 columns
 * Row height: 60px
 * 
 * Layout calculated to match current CSS grid exactly:
 * - Row 1: 4 stat cards (span-3 each)
 * - Row 2: Overview (span-6) + Alerts (span-6)
 * - Row 3: Expiring Certs table (span-12)
 * - Row 4: Recent Activity (span-12)
 */

export const DEFAULT_LAYOUT = [
  // Row 1: Stat Cards (4 widgets × 3 cols each = 12 cols total)
  { i: 'stat-active', x: 0, y: 0, w: 3, h: 3, minW: 3, minH: 2 },
  { i: 'stat-expiring', x: 3, y: 0, w: 3, h: 3, minW: 3, minH: 2 },
  { i: 'stat-requests', x: 6, y: 0, w: 3, h: 3, minW: 3, minH: 2 },
  { i: 'stat-acme', x: 9, y: 0, w: 3, h: 3, minW: 3, minH: 2 },
  
  // Row 2: System Overview + Alerts (2 widgets × 6 cols each = 12 cols)
  { i: 'overview', x: 0, y: 3, w: 6, h: 4, minW: 4, minH: 3 },
  { i: 'alerts', x: 6, y: 3, w: 6, h: 4, minW: 4, minH: 3 },
  
  // Row 3: Expiring Certificates Table (full width)
  { i: 'expiring-table', x: 0, y: 7, w: 12, h: 7, minW: 8, minH: 5 },
  
  // Row 4: Recent Activity (full width)
  { i: 'activity', x: 0, y: 14, w: 12, h: 5, minW: 8, minH: 4 },
];

/**
 * Responsive breakpoints matching Dashboard.module.css
 */
export const GRID_BREAKPOINTS = {
  lg: 1200,
  md: 996,
  sm: 768,
  xs: 480,
  xxs: 0,
};

export const GRID_COLS = {
  lg: 12,
  md: 12,
  sm: 6,
  xs: 4,
  xxs: 2,
};

/**
 * Load user layout from localStorage
 */
export function loadLayout() {
  try {
    const saved = localStorage.getItem('ucm-dashboard-layout');
    return saved ? JSON.parse(saved) : DEFAULT_LAYOUT;
  } catch (err) {
    console.error('Failed to load dashboard layout:', err);
    return DEFAULT_LAYOUT;
  }
}

/**
 * Save user layout to localStorage
 */
export function saveLayout(layout) {
  try {
    localStorage.setItem('ucm-dashboard-layout', JSON.stringify(layout));
  } catch (err) {
    console.error('Failed to save dashboard layout:', err);
  }
}

/**
 * Reset layout to default
 */
export function resetLayout() {
  localStorage.removeItem('ucm-dashboard-layout');
  return DEFAULT_LAYOUT;
}
