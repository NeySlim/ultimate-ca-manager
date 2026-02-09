# UCM Design System

## Typography

### Font Sizes
| Token | Size | Usage |
|-------|------|-------|
| `text-3xs` | 9px | Micro labels, badges |
| `text-2xs` | 10px | Compact table cells, small badges |
| `text-xs` | 12px | Secondary text, labels |
| `text-sm` | 14px | Body text, buttons |
| `text-base` | 16px | Primary content |
| `text-lg` | 18px | Section headers |
| `text-xl` | 20px | Page subtitles |
| `text-2xl` | 24px | Page titles |

### Font Families
- `font-sans` - Geist (UI text)
- `font-mono` - SF Mono (code, serials, hashes)

## Colors

### Background
| Token | Usage |
|-------|-------|
| `bg-bg-primary` | Main page background |
| `bg-bg-secondary` | Cards, panels |
| `bg-bg-tertiary` | Inputs, nested elements |

### Text
| Token | Usage |
|-------|-------|
| `text-text-primary` | Headings, important text |
| `text-text-secondary` | Body text |
| `text-text-tertiary` | Muted, placeholder |

### Status
| Token | Usage |
|-------|-------|
| `text-status-success` / `bg-status-success` | Valid, active, success |
| `text-status-warning` / `bg-status-warning` | Expiring, pending |
| `text-status-danger` / `bg-status-danger` | Expired, revoked, error |
| `text-status-info` / `bg-status-info` | Info, neutral |

### Accent
| Token | Usage |
|-------|-------|
| `text-accent-primary` / `bg-accent-primary` | Primary actions, links |
| `text-accent-secondary` / `bg-accent-secondary` | Secondary highlights |

### Status with Opacity
```jsx
// Background with 10% opacity
bg-status-success/10
bg-status-warning/10
bg-status-danger/10

// Background with 20% opacity (hover states)
bg-status-success/20
```

## Spacing

### Standard Scale
| Token | Size | Usage |
|-------|------|-------|
| `gap-1` | 4px | Tight inline elements |
| `gap-2` | 8px | Default gap (most common) |
| `gap-3` | 12px | Loose inline elements |
| `gap-4` | 16px | Section spacing |
| `p-2` | 8px | Compact padding |
| `p-3` | 12px | Card inner padding |
| `p-4` | 16px | Section padding |
| `px-3 py-2` | - | Button/input padding |

### Vertical Rhythm
```jsx
// Sections
<div className="space-y-4">  // 16px between sections

// Compact lists
<div className="space-y-2">  // 8px between items
```

## Border Radius

| Token | Size | Usage |
|-------|------|-------|
| `rounded-sm` | 2px | Subtle rounding |
| `rounded` | 4px | Default |
| `rounded-md` | 4px | Same as default |
| `rounded-lg` | 6px | Cards, panels (preferred) |
| `rounded-xl` | 8px | Large cards |
| `rounded-full` | 50% | Circles, pills |

**Preferred**: `rounded-lg` for most containers.

## Shadows

| Token | Usage |
|-------|-------|
| `shadow-sm` | Subtle elevation |
| `shadow-lg` | Cards, dropdowns |
| `shadow-xl` | Modals, overlays |

## Transitions

```jsx
// Color changes (buttons, links)
transition-colors duration-200

// All properties (complex animations)
transition-all duration-200

// Transform only
transition-transform duration-200
```

## Component Patterns

### Buttons
```jsx
<Button variant="primary" size="sm">Action</Button>
// Variants: primary, secondary, ghost, danger
// Sizes: sm, default, lg
```

### Badges
```jsx
<Badge variant="success">Active</Badge>
// Variants: success, warning, danger, info, purple, orange
```

### Cards
```jsx
<Card variant="elevated">
  <Card.Header icon={Icon} title="Title" />
  <Card.Body>Content</Card.Body>
</Card>
```

### Status Indicators
```jsx
// Dot indicator
<span className="w-2 h-2 rounded-full bg-status-success" />

// Badge style
<span className="px-2 py-0.5 rounded-full text-2xs bg-status-success/10 text-status-success">
  Active
</span>
```

### Icon Backgrounds
```jsx
// Use CSS classes from ThemeContext
<div className="icon-bg-blue">  // Blue themed
<div className="icon-bg-orange">  // Orange themed
<div className="icon-bg-violet">  // Purple themed
```

## Responsive Breakpoints

| Breakpoint | Min Width | Usage |
|------------|-----------|-------|
| (default) | 0px | Mobile |
| `sm:` | 640px | Large mobile |
| `md:` | 768px | Tablet |
| `lg:` | 1024px | Desktop |
| `xl:` | 1280px | Wide desktop |

### Common Patterns
```jsx
// Hide on mobile, show on desktop
<div className="hidden lg:block">

// Different padding
<div className="p-3 lg:p-4">

// Grid columns
<div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
```

## Theme Variables

Defined in `ThemeContext.jsx`, applied via CSS custom properties:

```css
--bg-primary
--bg-secondary
--bg-tertiary
--text-primary
--text-secondary
--text-tertiary
--border
--accent-primary
--accent-success
--accent-warning
--accent-danger
--accent-pro
```

### Icon Background Variables
```css
--icon-blue-bg
--icon-orange-bg
--icon-violet-bg
--icon-green-bg
--icon-red-bg
--icon-cyan-bg
```

## Do's and Don'ts

### ✅ Do
```jsx
// Use design tokens
<p className="text-sm text-text-secondary">

// Use semantic status colors
<span className="text-status-danger">

// Use consistent spacing
<div className="p-4 space-y-4">
```

### ❌ Don't
```jsx
// Hardcoded colors
<p className="text-gray-500">  // ❌
<span className="text-red-500">  // ❌

// Arbitrary values
<p className="text-[13px]">  // ❌ Use text-sm or text-xs

// Inline styles for colors
<div style={{ color: '#ff0000' }}>  // ❌
```
