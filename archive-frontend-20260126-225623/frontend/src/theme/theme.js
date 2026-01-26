/**
 * Theme utilities for UCM
 * Manages theme and accent color persistence
 */

const STORAGE_KEY_THEME = 'ucm-theme';
const STORAGE_KEY_ACCENT = 'ucm-accent';

const THEMES = ['dark', 'light'];
const ACCENTS = ['blue', 'green', 'purple', 'orange', 'red', 'cyan'];

const DEFAULT_THEME = 'dark';
const DEFAULT_ACCENT = 'blue';

/**
 * Get current theme from localStorage or default
 */
export function getTheme() {
  const saved = localStorage.getItem(STORAGE_KEY_THEME);
  return THEMES.includes(saved) ? saved : DEFAULT_THEME;
}

/**
 * Get current accent from localStorage or default
 */
export function getAccent() {
  const saved = localStorage.getItem(STORAGE_KEY_ACCENT);
  return ACCENTS.includes(saved) ? saved : DEFAULT_ACCENT;
}

/**
 * Set theme and update HTML attributes
 */
export function setTheme(theme) {
  if (!THEMES.includes(theme)) {
    console.warn(`Invalid theme: ${theme}`);
    return;
  }
  
  localStorage.setItem(STORAGE_KEY_THEME, theme);
  document.documentElement.setAttribute('data-theme', theme);
}

/**
 * Set accent and update HTML attributes
 */
export function setAccent(accent) {
  if (!ACCENTS.includes(accent)) {
    console.warn(`Invalid accent: ${accent}`);
    return;
  }
  
  localStorage.setItem(STORAGE_KEY_ACCENT, accent);
  document.documentElement.setAttribute('data-accent', accent);
}

/**
 * Initialize theme system on app load
 */
export function initTheme() {
  const theme = getTheme();
  const accent = getAccent();
  
  document.documentElement.setAttribute('data-theme', theme);
  document.documentElement.setAttribute('data-accent', accent);
  
  return { theme, accent };
}

/**
 * Toggle between dark and light theme
 */
export function toggleTheme() {
  const current = getTheme();
  const next = current === 'dark' ? 'light' : 'dark';
  setTheme(next);
  return next;
}

export { THEMES, ACCENTS, DEFAULT_THEME, DEFAULT_ACCENT };
