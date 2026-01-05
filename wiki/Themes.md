# Theme Customization Guide

UCM features 8 beautiful themes with complete light and dark mode support.

---

## 🎨 Available Themes

### Sentinel (Default)
- **Light**: Professional blue/gray palette, clean and modern
- **Dark**: Deep navy with bright accents, easy on the eyes
- **Best For**: Professional environments, corporate use

### Amber
- **Light**: Warm orange and amber tones, energetic
- **Dark**: Rich dark background with golden highlights
- **Best For**: Creative teams, design-focused organizations

### Blossom
- **Light**: Soft pink and purple gradients, elegant
- **Dark**: Deep purple with vibrant pink accents
- **Best For**: Modern startups, design agencies

### Nebula
- **Light**: Purple and magenta cosmic theme, unique
- **Dark**: Deep space purple with brilliant magenta
- **Best For**: Tech companies, innovation teams

---

## 🔄 Changing Themes

### Method 1: From Header (Logged In)

1. Click the **palette icon** (🎨) in the top-right header
2. A dropdown appears with 8 theme options
3. Click any theme to apply immediately
4. **OR** use the **moon/sun toggle** to switch light/dark mode only

**Features**:
- ✅ Instant application (no page reload)
- ✅ Preference saved to localStorage
- ✅ Persists across sessions

### Method 2: From Settings Page

1. Go to **Settings** (sidebar or user menu)
2. Scroll to **"Theme Preferences"** section
3. See visual gallery of all 8 themes
4. Click any theme card to select
5. Theme applies immediately

**Features**:
- ✅ Visual preview of all themes
- ✅ Direct selection with one click
- ✅ Shows active theme with highlight

### Method 3: From Login Page (Before Authentication)

1. On the login page, find the theme selector
2. Click the **palette icon dropdown**
3. Select your preferred theme
4. **OR** use moon/sun toggle for light/dark
5. Login with your chosen theme

**Features**:
- ✅ Choose theme before logging in
- ✅ Theme persists after authentication
- ✅ Same theme for all sessions

---

## 🌓 Light vs Dark Mode

### Automatic Detection
UCM can detect your OS/browser preference:
```javascript
// Auto-detect dark mode
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
```

### Manual Override
1. Use the **moon icon** (🌙) to switch to dark mode
2. Use the **sun icon** (☀️) to switch to light mode
3. Selection overrides system preference

### What Changes?
- **Backgrounds**: Light → white/gray | Dark → black/navy
- **Text**: Light → dark gray | Dark → white/light gray
- **Accents**: Maintains theme color (blue, amber, pink, purple)
- **Scrollbars**: Light themes → dark scrollbars | Dark themes → light scrollbars
- **Shadows**: Adjusted for contrast

---

## 🎨 Theme Features

### Custom CSS Variables

All themes use CSS variables for consistency:

```css
:root {
  /* Colors */
  --primary-color: #3b82f6;      /* Theme accent */
  --success-color: #10b981;
  --danger-color: #ef4444;
  --warning-color: #f59e0b;
  
  /* Text */
  --text-primary: #1f2937;       /* Main text */
  --text-secondary: #6b7280;     /* Secondary text */
  --text-muted: #9ca3af;         /* Muted text */
  
  /* Backgrounds */
  --bg-primary: #ffffff;         /* Main background */
  --bg-secondary: #f9fafb;       /* Secondary background */
  --card-bg: #ffffff;            /* Card background */
  
  /* UI Elements */
  --border-color: #e5e7eb;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
}
```

### Themed Scrollbars

**Light Themes**:
- Scrollbar track: Light gray
- Scrollbar thumb: Dark gray (for contrast)
- Hover: Darker gray

**Dark Themes**:
- Scrollbar track: Dark gray/black
- Scrollbar thumb: Light gray (for visibility)
- Hover: Lighter gray

**Browser Support**:
- ✅ Chrome/Edge (WebKit)
- ✅ Firefox (experimental)
- ⚠️ Safari (partial support)

### Component Theming

All UI components respect theme colors:
- **Buttons**: Primary, secondary, danger, success
- **Badges**: Success, danger, warning, info, secondary
- **Cards**: Background, border, shadow
- **Forms**: Inputs, selects, textareas
- **Modals**: Backdrop, container, content
- **Tables**: Headers, rows, hover effects
- **Sidebar**: Background, links, hover states

---

## 🛠️ Customizing Themes (Advanced)

### Creating a Custom Theme

1. **Copy an existing theme file**:
   ```bash
   cd /opt/ucm/frontend/static/css/themes/
   cp sentinel-light.css custom-light.css
   ```

2. **Edit CSS variables**:
   ```css
   :root {
     --primary-color: #your-color;
     --bg-primary: #your-bg;
     /* ... modify all variables ... */
   }
   ```

3. **Register theme in theme-switcher.js**:
   ```javascript
   const themes = {
     // ... existing themes ...
     'custom-light': 'Custom Light',
     'custom-dark': 'Custom Dark'
   };
   ```

4. **Add to theme selector**:
   - Update `base.html` theme dropdown
   - Update `settings.html` theme gallery
   - Add theme preview card

### Theme File Structure

```
frontend/static/css/themes/
├── sentinel-light.css       # Default light theme
├── sentinel-dark.css        # Default dark theme
├── amber-light.css
├── amber-dark.css
├── blossom-light.css
├── blossom-dark.css
├── nebula-light.css
└── nebula-dark.css
```

### JavaScript Integration

**theme-switcher.js** handles:
- localStorage persistence
- Dynamic CSS loading
- Theme switching logic
- Light/dark mode toggle

**Location**: `/opt/ucm/frontend/static/js/theme-switcher.js`

---

## 📊 Theme Comparison

| Theme | Primary Color | Use Case | Mood |
|-------|--------------|----------|------|
| **Sentinel** | Blue (#3b82f6) | Corporate, Professional | Trust, Stability |
| **Amber** | Orange (#f59e0b) | Creative, Energetic | Warmth, Energy |
| **Blossom** | Pink (#ec4899) | Modern, Elegant | Beauty, Creativity |
| **Nebula** | Purple (#a855f7) | Tech, Innovation | Mystery, Innovation |

---

## 🔍 Troubleshooting

### Theme Not Changing
1. ✅ Clear browser cache: `Ctrl+Shift+Delete`
2. ✅ Check localStorage: `localStorage.getItem('theme')`
3. ✅ Hard reload: `Ctrl+Shift+R`
4. ✅ Try different browser

### Theme Resets on Login
1. ✅ Verify localStorage is enabled
2. ✅ Check browser privacy settings (allow cookies/storage)
3. ✅ Try selecting theme again from login page

### Scrollbars Not Themed
1. ✅ Check browser support (Chrome/Edge recommended)
2. ✅ Verify theme CSS file loaded: Inspect → Sources
3. ✅ Clear cache and reload

### Custom Theme Not Showing
1. ✅ Verify CSS file syntax: `W3C CSS Validator`
2. ✅ Check file path in `theme-switcher.js`
3. ✅ Reload theme selector dropdown
4. ✅ Check browser console for errors

### Colors Look Wrong
1. ✅ Verify correct theme file loaded (Inspect → Sources)
2. ✅ Check CSS variable values in `:root`
3. ✅ Test in different browser
4. ✅ Clear browser cache

---

## 📱 Mobile Theming

All themes are fully responsive:
- ✅ Touch-friendly theme selector
- ✅ Optimized for small screens
- ✅ Same theme persists on mobile
- ✅ Readable text sizes
- ✅ Proper contrast ratios

**Mobile-Specific**:
- Larger touch targets (44x44px minimum)
- Simplified theme selector on small screens
- Single-column layout for theme gallery

---

## ♿ Accessibility

### WCAG AA Compliance

All themes meet WCAG AA standards:
- ✅ **Text Contrast**: 4.5:1 minimum (normal text)
- ✅ **Large Text Contrast**: 3:1 minimum (18pt+)
- ✅ **UI Component Contrast**: 3:1 minimum (buttons, borders)
- ✅ **Focus Indicators**: Visible keyboard focus
- ✅ **Color Independence**: Not relying on color alone

### Testing Contrast

Use browser DevTools or online tools:
```bash
# Lighthouse in Chrome DevTools
Ctrl+Shift+I → Lighthouse → Accessibility

# Online tool
https://webaim.org/resources/contrastchecker/
```

### High Contrast Mode

For users with visual impairments:
1. Use **Sentinel Dark** for maximum contrast
2. Enable OS high contrast mode (Windows/macOS)
3. Browser zoom: `Ctrl + +` to increase text size

---

## 📚 Related Pages

- [User Settings](User-Settings)
- [Dashboard Overview](Dashboard)
- [Troubleshooting](Troubleshooting)

---

**Last Updated**: 2026-01-05
