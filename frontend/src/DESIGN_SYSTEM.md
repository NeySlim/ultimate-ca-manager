# UCM Design System

> Source of truth: `src/styles/tokens.css` (colour tokens), `src/index.css`
> (non-colour tokens, component classes),
> `src/contexts/ThemeContext.jsx` (family and mode selection) and
> `tailwind.config.js` (Tailwind aliases). This document describes what those
> files actually implement. `src/lib/__tests__/designTokens.test.js` and
> `opacityClasses.test.js` fail the suite when the source uses a token, class or
> `var(--x)` that none of them declares.

## Theming model

Colors are **not** hardcoded. `ThemeContext.jsx` sets `data-theme` and
`data-mode` on `<html>`; `styles/tokens.css` holds one block per
`[data-theme][data-mode]` pair (bare `:root` = Atelier dark, the fallback).
There are **4 theme families** × **2 modes**:

| Family | `id` | Accent | Modes |
|--------|------|--------|-------|
| Atelier (default) | `atelier` | `#4F8EF7` | dark / light |
| Aurore | `aurore` | `#6b78e0` | dark / light |
| Purple Night | `purple` | `#A855F7` | dark / light |
| Orange Sunset | `sunset` | `#F97316` | dark / light |

A stored `gray` (localStorage or server preference) reads as `atelier`; the
next write persists `atelier`.

### The 21 tokens

| Token | Role |
|-------|------|
| `--bg` `--panel` `--raised` `--hover` | Page, card, raised and hover surfaces |
| `--text` `--muted` | Primary and secondary text |
| `--line` | Decorative divider |
| `--control` | Border of controls (3:1 on `--bg`) |
| `--accent` `--selected` `--on-accent` | Accent, selected-row background, and the text colour on accent, good and bad button fills |
| `--good` `--goodbg` `--warn` `--warn-fill` `--warnbg` `--bad` `--badbg` | Status text, tinted backgrounds, and the amber fill |
| `--grad-a` `--grad-b` `--glow` | Aurore gradient and halo (accent for the other families) |

`themeContrast.test.js` enforces WCAG on all 8 palettes: 4.5:1 for text pairs,
3:1 for `--accent`, `--control` and `--warn-fill` on `--bg`. All text is 4.5:1, `--on-accent`
included (on the accent, good and bad gradients, and on `--grad-a`/`--grad-b` for Aurore), as is
`--text-tertiary` on `--bg` and `--panel`. `--line` is
decorative and exempt. `themeBaseline.test.js` pins every value in
`styles/tokens.baseline.json`: change a value, update the baseline in the same
commit (`UPDATE_THEME_BASELINE=1 npx vitest run src/lib/__tests__/themeBaseline.test.js`).

### Compatibility aliases (being retired)

The pre-Atelier names (`--bg-primary`, `--text-secondary`, `--accent-danger`,
`--border`, `--detail-*`, `--icon-*`, `--gradient-*`, `--logo-gradient-*`…) are
defined once in `tokens.css` from the tokens above, so existing pages keep
rendering. New code uses the 21 tokens; an alias goes away when its last
consumer does. Icon hues, `--violet` and the logo gradient depend on the mode
only, not on the family.

**Rule.** No `#rrggbb`, `rgb()`/`rgba()`/`hsl()` literal and no Tailwind palette class
(`text-red-500`, `bg-white`, `border-gray-800`) in `src`: use a token, an alias or a helper class.
Three constants (`--ink`, `--paper`, `--scrim`) are declared in each of the 8 palettes and pinned in the baseline; `bg-scrim-NN` is the overlay. There is no `--hue-*` token.
`styles/__tests__/noHardcodedColors.test.js` enforces it and lists the exceptions with their reason.

Mode resolves from `system` / `dark` / `light` (persisted in localStorage +
server prefs). Every component must read tokens (`var(--…)` or the Tailwind
aliases below) so it adapts to all 8 combinations. Never hardcode a hex.

Documented exceptions carry fixed colors in every theme: the Ko-fi tokens
(`--kofi-coral`, `--kofi-coral-strong`, `--kofi-coral-hover`, used by
`.kofi-card` / `.kofi-badge` / `.kofi-button` / `.kofi-icon`) because they are a
third party's brand, `ProviderIcons.jsx`, the theme picker swatches, the help reader's
sepia palette, and the email preview canvas.

## Typography

### Font Sizes
| Token | Size | Usage |
|-------|------|-------|
| `text-3xs` | 12px | Micro labels, badges (12px floor, same as `text-xs`) |
| `text-2xs` | 12px | Compact table cells, small badges (12px floor) |
| `text-xs` | 12px | Secondary text, labels |
| `text-sm` | 14px | Body text, buttons |
| `text-base` | 16px | Primary content |
| `text-lg` | 18px | Section headers |
| `text-xl` | 20px | Page subtitles |
| `text-2xl` | 24px | Page titles |

`minFontSize.test.js` fails if `index.css`, `tokens.css` or `tailwind.config.js`
declare a size below 12px, or if a component uses an arbitrary `text-[N]` class
below 12px. Inline `fontSize` styles are not covered.

### Font Families
- `font-sans` — Inter (UI text), self-hosted (`/fonts/Inter-*.woff2`)
- `font-mono` — Fira Code (code, serials, hashes), self-hosted. `.font-mono`
  also applies `font-size: 0.92em; letter-spacing: -0.01em` (Fira runs wide).

## Colors

All values below are the **Atelier / dark** defaults; they shift per theme family
and mode. Tailwind aliases (`tailwind.config.js`) map to the CSS vars.

### Background
| Tailwind alias | CSS var | Usage |
|----------------|---------|-------|
| `bg-bg-primary` | `--bg-primary` | Main page background |
| `bg-bg-secondary` | `--bg-secondary` | Cards, panels |
| `bg-bg-tertiary` / `bg-bg-hover` | `--bg-tertiary` | Inputs, nested elements, hover fill |

### Text
| Tailwind alias | CSS var | Usage |
|----------------|---------|-------|
| `text-text-primary` | `--text-primary` | Headings, important text |
| `text-text-secondary` | `--text-secondary` | Body text |
| `text-text-tertiary` | `--text-tertiary` | Muted, placeholder, help text |

### Accent & status
| Tailwind alias | CSS var | Usage |
|----------------|---------|-------|
| `accent-primary` | `--accent-primary` | Primary actions, links |
| `accent-pro` | `--accent-pro` | "Pro"/highlight accent (purple/pink, theme-dependent) |
| `status-success` / `accent-success` | `--accent-success` | Valid, active |
| `status-warning` / `accent-warning` | `--accent-warning` | Expiring, pending |
| `status-danger` / `status-error` / `accent-danger` | `--accent-danger` | Expired, revoked, error |
| `status-info` | `--accent-primary` | Info, neutral |
| `border` | `--border` | Default borders |
| `border-strong` | `--border-strong` | Emphasised borders (outline button hover, floating windows) |
| `border-hover` | `--text-tertiary` | Border on hover |

`--accent-purple` exists only as a CSS var (no Tailwind alias): it backs the
`status-purple-*` tints and `Card accent="purple"`.

> **These tokens do not exist**: `accent-secondary`, `accent` (bare),
> `text-muted`, `border-primary`, `status-*-foreground`, `--status-danger`,
> `--status-error`, `--status-warning`, `--accent-info`. A class or `var()`
> naming them renders nothing, and `designTokens.test.js` fails on it. Use
> `accent-pro`, `accent-primary`, `text-tertiary`, `border` and the
> `--accent-*` vars instead.

### Opacity with CSS-var colors — use the helper classes
Tailwind's `/opacity` syntax does **not** work on these var-backed colors:
`bg-bg-tertiary/40` is dropped from the build. `index.css` hand-writes
`color-mix()` helpers named `<utility>-<token>-opNN`, with `hover:`,
`focus:` and `enabled:hover:` variants where the UI needs them:

- Surfaces: `bg-primary-op50/80/90`, `bg-secondary-op10…op95`, `bg-tertiary-op30/40/50/60/80`.
- Accent: `bg-accent-primary-op5…op80`, `border-accent-primary-op20…op50`,
  `ring-accent-primary-op30/40/50`, `text-accent-primary-op60`,
  `from-accent-primary-op5`, `to-accent-primary-op70`.
- Status: `bg-status-{success,warning,danger,info}-opNN` and
  `border-status-…-opNN` at the steps the UI uses (5 to 40), and the same
  families under the `accent-` spelling.
- Border and text: `border-border-op30/40/50/60`, `divide-border-op30`,
  `text-secondary-op60`, `text-tertiary-op50`, `placeholder-secondary-op60`.

The exact list is the set of `-opNN` selectors in `index.css`;
`opacityClasses.test.js` fails when the markup uses one that is not declared.
Add the missing rule rather than rounding to a neighbour.

### Status tints (theme-aware classes)
For each of `success`, `warning`, `danger` and `primary` (info):
`status-X-bg` (soft tint), `status-X-bg-solid`, `status-X-text`,
`status-X-border`, `status-X-glow`, and the composite `status-X-badge`
(tint + text + border). `status-purple-*` has only `bg`, `bg-solid`, `text`
and `border`; `status-orange-*` and `status-yellow-*` are derived from
`--accent-warning`. `status-badge-{success,warning,danger}` are the
gradient variants used by `badge-enhanced`.

### Icon background classes (mode-aware, set by tokens.css)
Colored tile backgrounds that avoid "ton sur ton" clashes per theme:
`icon-bg-blue`, `icon-bg-orange`, `icon-bg-amber`, `icon-bg-emerald` /
`icon-bg-green`, `icon-bg-teal` / `icon-bg-cyan`, `icon-bg-violet` /
`icon-bg-purple`, backed by `--icon-{blue,orange,amber,emerald,teal,violet}-{bg,text}`.
Derived from status tokens: `icon-bg-red` (`--accent-danger`),
`icon-bg-gray` (`--text-tertiary`).

### Detail panel tokens
`tokens.css` also defines `--gradient-bg` and the `--detail-*` set
(`detail-header-bg/border/shadow`, `detail-icon-bg/shadow`,
`detail-stats-border`, `detail-section-bg/border`, `detail-field-bg/border`),
consumed by the detail panel classes in `index.css`.

## Spacing

| Token | Size | Usage |
|-------|------|-------|
| `gap-1` / `p-1` | 4px | Tight inline |
| `gap-2` / `p-2` | 8px | Default gap (most common) |
| `gap-3` / `p-3` | 12px | Card inner padding |
| `gap-4` / `p-4` | 16px | Section spacing |
| `px-3 py-2` | — | Button/input padding |

Vertical rhythm: `space-y-4` between sections, `space-y-2` for compact lists.

## Border Radius

| Token | Size | Usage |
|-------|------|-------|
| `rounded-sm` | 2px | Subtle |
| `rounded` / `rounded-md` | 4px | Default |
| `rounded-lg` | 6px | Cards, panels |
| `rounded-xl` | 8px | Large cards |
| `rounded-full` | 50% | Circles, pills |

Card classes (`card-soft`, `card-interactive`) use a literal `12px` radius.
Button classes (`btn-gradient`, `btn-soft`, `btn-danger-soft`,
`btn-warning-soft`) use `8px`; the `ghost` and `outline` variants keep the
`rounded-md` 4px of the base.

## Shadows & elevation

`index.css` defines a layered shadow scale (not plain Tailwind shadows):

| Var | Class | Usage |
|-----|-------|-------|
| — | `elevation-0` | No shadow |
| `--shadow-xs` | — | Resting cards (`card-soft`) and `btn-soft` |
| `--shadow-sm` | `elevation-1` | Resting buttons, hover lift |
| `--shadow-md` | `elevation-2` | Elevated cards |
| `--shadow-lg` | `elevation-3` | Dropdowns, popovers |
| `--shadow-xl` | `elevation-4` | Modals, overlays |

`elevation-glow-{primary,success,danger}` add `--shadow-glow-*` to `--shadow-md`.
Extras: `--shadow-glow-{primary,success,danger,warning}` (focus/hover glow),
`--shadow-inner-highlight`, `--shadow-inner-sm`, `--floating-window-shadow`.

## Gradients

| Var | Usage |
|-----|-------|
| `--gradient-primary` | Primary gradient buttons (`btn-gradient`) |
| `--gradient-success` / `--gradient-danger` | Success/danger gradient buttons |
| `--gradient-surface` | Panel surfaces |
| `--gradient-shine` | Highlight sheen |
| `--gradient-accent` (per theme) | Brand gradient (from `--gradient-from`/`--gradient-to`) |
| `--logo-gradient-{start,mid,end,accent}` | Logo gradient: dark `#fb923c → #f97316 → #ea580c`, light `#ea580c → #c2410c → #9a3412` |

## Glassmorphism

`--glass-blur` (12px), `--glass-bg`, `--glass-border`, `--glass-shadow` — used
for floating panels / overlays.

## Motion (timing & easing)

| Var | Value | Use |
|-----|-------|-----|
| `--duration-fast` | 150ms | Transforms, taps |
| `--duration-normal` | 250ms | Color/box-shadow |
| `--duration-slow` | 400ms | Large transitions |
| `--ease-smooth` | `cubic-bezier(0.4,0,0.2,1)` | Default |
| `--ease-out` / `--ease-bounce` / `--ease-spring` | — | Entrances, playful motion |

Keyframe animations (Tailwind): `animate-fade-in`, `animate-slide-up`,
`animate-slide-in-right`, `animate-pulse-slow`.

## Component Patterns

### Buttons (`components/Button.jsx`)
```jsx
<Button variant="primary" size="sm">Action</Button>
<Button type="submit" loading={saving} loadingText={t('common.saving')}>Save</Button>
```
- **Variants**: `primary` (gradient — `btn-gradient`), `secondary` (`btn-soft`),
  `success`, `danger` (gradient), `danger-soft`, `warning-soft`, `ghost`,
  `outline`. Non-gradient variants get a `focus-ring`.
- **Sizes**: `xs`, `sm` (default), `default`, `lg`.
- **`type` defaults to `button`**, not the HTML `submit`: a button inside a
  form never submits it by accident. A submit button passes `type="submit"`.
- `loading` disables the button and shows a spinner + `loadingText`; it wins
  over an explicit `disabled={false}`.

`primary` is a **gradient with a shine sweep on hover** (`--gradient-primary`),
not a flat `bg-accent-primary`. Match this when rebuilding buttons elsewhere.

### Badges (`components/Badge.jsx`)
```jsx
<Badge variant="success" dot pulse icon={Icon}>Active</Badge>
```
- **Semantic variants**: `default`, `primary`, `secondary`, `success`,
  `warning`, `danger`, `info`, `outline`.
- **Color aliases** (theme-aware): `emerald`, `red`, `blue`, `yellow`,
  `purple`/`violet`, `amber`, `orange`, `cyan`/`teal`, `gray`.
- **Props**: `dot` (status dot), `pulse` (animate dot), `icon`, `size`
  (`sm` pill / `default` / `lg`). Base class `badge-enhanced`.
- Helpers: `<ExperimentalBadge />`, `<CATypeIcon isRoot />`.

### Cards (`components/Card.jsx`)
```jsx
<Card variant="elevated" accent="primary">
  <Card.Header icon={Icon} iconColor="primary" title="Title" subtitle="…" action={…} />
  <Card.Body>Content</Card.Body>
  <Card.Footer>…</Card.Footer>
</Card>
```
- **Variants**: `default`/`soft` (`card-soft`), `elevated` (`elevation-2`),
  `bordered`. `interactive` makes it a clickable card with a lift effect
  (`card-interactive`: `translateY(-2px)` + accent-tinted border on hover).
- **`accent`** left-border: `primary`, `success`, `warning`, `danger`, `info`,
  `purple`.
- `Card.Header` renders an `IconBadge` + `section-header-gradient`.

### Status indicators
```jsx
<span className="w-2 h-2 rounded-full status-success-bg-solid" />
<span className="px-2 py-px rounded-full text-2xs status-success-bg status-success-text">Active</span>
```

## Responsive Breakpoints

| Breakpoint | Min Width |
|------------|-----------|
| (default) | 0px (mobile) |
| `sm:` | 640px |
| `md:` | 768px |
| `lg:` | 1024px |
| `xl:` | 1280px |

## Do's and Don'ts

### Do
```jsx
<p className="text-sm text-text-secondary">          // design tokens
<span className="status-danger-text">                // semantic status
<div className="p-4 space-y-4">                      // consistent spacing
<div className="bg-tertiary-op40">                   // var-color opacity helper
<div style={{ color: 'var(--accent-danger)' }}>      // a declared var when a class cannot do
```

### Don't
```jsx
<p className="text-gray-500">                         // BAD — hardcoded palette
<div style={{ color: '#ff0000' }}>                    // BAD — inline hex
<p className="text-[13px]">                            // BAD — arbitrary size
<div className="bg-bg-tertiary/40">                    // BAD — /opacity on var color
<span className="text-accent-secondary">              // BAD — token doesn't exist
<p className="text-text-muted">                       // BAD — token doesn't exist (text-text-tertiary)
<div style={{ color: 'var(--status-danger)' }}>       // BAD — var never set (--accent-danger)
```
