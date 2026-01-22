/**
 * Dashboard Grid Layout Configuration
 * 
 * Grid system: 24 columns (double granularity for finer control)
 * Row height: 30px (half of previous 60px for more vertical precision)
 * 
 * Layout calculated to match current CSS grid exactly:
 * - Row 1: 4 stat cards (span-6 each = 24 cols)
 * - Row 2: Overview (span-12) + Alerts (span-12)
 * - Row 3: Expiring Certs table (span-24)
 * - Row 4: Recent Activity (span-24)
 * 
 * With 24 columns, users can:
 * - Make widgets as small as 1/6 width (4 cols)
 * - Resize in finer increments (1 col = ~4% width)
 * - Place up to 6 stat cards in a row
 * 
 * With 30px row height, users can:
 * - Adjust heights in 30px increments
 * - Create taller/shorter widgets more precisely
 */

export const DEFAULT_LAYOUT = [
  // Row 1: Stat Cards (4 widgets × 6 cols each = 24 cols total)
  { i: 'stat-active', x: 0, y: 0, w: 6, h: 5, minW: 4, minH: 3 },
  { i: 'stat-expiring', x: 6, y: 0, w: 6, h: 5, minW: 4, minH: 3 },
  { i: 'stat-requests', x: 12, y: 0, w: 6, h: 5, minW: 4, minH: 3 },
  { i: 'stat-acme', x: 18, y: 0, w: 6, h: 5, minW: 4, minH: 3 },
  
  // Row 2: System Overview + Alerts (2 widgets × 12 cols each = 24 cols)
  { i: 'overview', x: 0, y: 5, w: 12, h: 7, minW: 6, minH: 5 },
  { i: 'alerts', x: 12, y: 5, w: 12, h: 7, minW: 6, minH: 5 },
  
  // Row 3: Expiring Certificates Table (full width)
  { i: 'expiring-table', x: 0, y: 12, w: 24, h: 12, minW: 12, minH: 8 },
  
  // Row 4: Recent Activity (full width)
  { i: 'activity', x: 0, y: 24, w: 24, h: 10, minW: 12, minH: 6 },
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
  lg: 24,
  md: 24,
  sm: 12,
  xs: 8,
  xxs: 4,
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
