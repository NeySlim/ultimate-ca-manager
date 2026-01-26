# UCM Frontend v2.1

Modern React frontend for Unified Certificate Manager.

## 🎯 Overview

Complete redesign with React 18, Vite 5, and Headless UI. Features a comprehensive PKI management interface with theme system, intelligent color mapping, and responsive design.

## 🚀 Quick Start

### Development

```bash
npm install
npm run dev
```

Open http://localhost:5173

### Production Build

```bash
npm run build
```

Output: `static/` directory (ready for deployment)

### Preview Production Build

```bash
npm run preview
```

## 📦 Tech Stack

- **React** 18.2 - UI library
- **Vite** 5.0 - Build tool
- **React Router** 7.12 - Routing
- **Headless UI** 2.2.9 - Accessible components
- **Phosphor Icons** 2.1.10 - Icon system
- **react-hot-toast** 2.6.0 - Notifications
- **date-fns** 4.1.0 - Date formatting

## 🎨 Theme System

### 12 Theme Configurations

2 themes × 6 accent colors:
- **Themes**: Dark, Light
- **Accents**: Blue, Green, Purple, Orange, Red, Cyan

### Usage

Themes are automatically persisted in localStorage:

```javascript
import { setTheme, setAccent } from './theme/theme';

setTheme('dark');      // 'dark' or 'light'
setAccent('blue');     // 'blue', 'green', 'purple', 'orange', 'red', 'cyan'
```

### CSS Variables

All design tokens in `src/theme/variables.css`:

```css
var(--bg-primary)       /* Main background */
var(--bg-secondary)     /* Secondary background */
var(--bg-tertiary)      /* Tertiary background (accent-tinted) */
var(--text-primary)     /* Primary text */
var(--text-secondary)   /* Secondary text */
var(--accent-primary)   /* Accent color */
var(--radius)           /* Border radius (3px) */
```

## 🧩 Component Library

### UI Components (`src/components/ui/`)

Atomic design components:

- **Button** - 4 variants (default, primary, success, danger)
- **Badge** - 5 variants (success, warning, danger, info, secondary)
- **Input** - Text, password, with label/error support
- **Icon** - Phosphor wrapper with gradient support
- **Card** - Header/Body composition
- **Tabs** - Headless UI wrapper

### Domain Components (`src/components/domain/`)

Business logic components:

- **ActivityFeed** - Activity timeline with gradient icons
- **StatCard** - Dashboard stat widget with trends
- **DataTable** - Sortable table with empty/loading states
- **SearchToolbar** - Search + filters + actions
- **CAHierarchy** - Certificate Authority tree view

## 📄 Pages

14 pages organized by function:

### Dashboard & Logs
- **Dashboard** - StatCards + Activity + Expiring Certs
- **Activity Log** - App Logs + PKI Operations (2 tabs)

### PKI Management
- **CAs** - List/Hierarchy view toggle
- **Certificates** - 8 columns, advanced filters
- **CSRs** - Pending/Approved/Rejected workflow (3 tabs)
- **Templates** - Certificate templates grid
- **CRL/OCSP** - CRL Management + OCSP Config (2 tabs)

### Protocols
- **ACME** - Internal + Let's Encrypt (2 tabs)
- **SCEP** - Configuration + Enrollments (2 tabs)

### System
- **Import** - CA/Certificate/OPNsense (3 tabs)
- **Trust Store** - System + Custom (2 tabs)
- **Users** - User management table
- **Settings** - General/Email/Security/Backup (4 tabs)
- **Profile** - Account/Security/Activity/Preferences (4 tabs)

## 🎯 Design System

### Strict Compliance

All measurements from `prototype-dashboard.html`:

- **Button height**: 26px (strict)
- **Input height**: 30px (strict)
- **Border radius**: 3px everywhere
- **Font sizes**: 13px body, 11px labels
- **Form max-width**: 400px (prevents stretching)
- **Icons**: Outline only (never ph-fill)

### Intelligent Color Mapping

Context-aware badge/icon variants:

```javascript
import { getBadgeVariant } from './utils/getBadgeVariant';

getBadgeVariant('cert-status', 'valid');     // → 'success'
getBadgeVariant('cert-status', 'expired');   // → 'danger'
getBadgeVariant('ca-type', 'root');          // → 'info'
getBadgeVariant('user-role', 'admin');       // → 'danger' (red = power)
```

### Responsive Breakpoints

```css
@media (max-width: 1200px) { /* Tablet */ }
@media (max-width: 768px)  { /* Mobile */ }
```

## 🔧 Development

### Project Structure

```
src/
├── components/
│   ├── ui/             # Atomic components (Button, Badge, Input, etc.)
│   ├── domain/         # Business components (DataTable, ActivityFeed, etc.)
│   ├── layout/         # Layout components (Sidebar, Topbar, AppLayout)
│   └── ErrorBoundary.jsx
├── pages/              # 14 pages (Dashboard, CAs, Certificates, etc.)
├── routes/             # React Router configuration
├── services/           # Mock data services (mockData.js)
├── theme/              # Theme system (variables.css, theme.js)
├── utils/              # Utilities (classNames, getBadgeVariant, etc.)
├── hooks/              # Custom hooks (useToast, useModal)
├── App.jsx
└── main.jsx
```

### CSS Architecture

- **CSS Modules** for component-scoped styles
- **Global variables** in `src/theme/variables.css`
- **No CSS-in-JS** (performance)

### Mock Data

All pages use realistic mock data from `src/services/mockData.js`:

```javascript
import { getDashboardStats, getRecentActivity } from '../services/mockData';

const stats = getDashboardStats();  // { cas: {...}, certificates: {...}, ... }
const activity = getRecentActivity(); // [{ icon, text, time, user }, ...]
```

15 service functions, 250+ realistic records.

## 🚢 Production Deploy

### Build for Production

```bash
npm run build
```

Generates optimized bundle in `static/`:
- Code splitting per route (React.lazy)
- Minified JS/CSS
- Gzip compression

### Deploy to UCM Server

```bash
# Copy build output to UCM static directory
cp -r static/* /opt/ucm/frontend/static/
```

### Current Build Stats

- **Modules**: 320
- **JS**: 355KB (108KB gzip)
- **CSS**: 46KB (7KB gzip)
- **Build time**: ~1.4s

## 🎨 Customization

### Adding a New Page

1. Create page component in `src/pages/`
2. Add lazy import in `src/routes/index.jsx`
3. Add route configuration
4. Add navigation link in `src/components/layout/Sidebar.jsx`

### Adding Mock Data

Add service function in `src/services/mockData.js`:

```javascript
export function getMyData() {
  return [
    { id: 1, name: 'Example', status: 'active' },
    // ...
  ];
}
```

### Customizing Theme

Edit `src/theme/variables.css`:

```css
[data-theme="dark"][data-accent="blue"] {
  --accent-primary: hsl(207, 90%, 54%);
  /* ... */
}
```

## 📚 Additional Resources

- **Design Reference**: `prototype-dashboard.html` (in project root)
- **API Reference**: `API_REFERENCE.md`
- **Component Docs**: JSDoc comments in component files

## 🐛 Troubleshooting

### Build Errors

```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

### Theme Not Persisting

Check browser localStorage:
```javascript
localStorage.getItem('ucm-theme');  // 'dark' or 'light'
localStorage.getItem('ucm-accent'); // 'blue', 'green', etc.
```

### Icons Not Displaying

Ensure Phosphor Icons are loaded:
```html
<link rel="stylesheet" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/regular/style.css">
```

## 📝 License

Proprietary - UCM v2.1

---

**Built with ❤️ for UCM v2.1**
