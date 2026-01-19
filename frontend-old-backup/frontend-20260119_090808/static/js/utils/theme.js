const ThemeManager = {
  STORAGE_KEY: 'ucm-theme',
  init() {
    this.applyTheme(this.getPreferredTheme());
    this.watchSystemPreference();
  },
  getPreferredTheme() {
    const stored = localStorage.getItem(this.STORAGE_KEY);
    if (stored) return stored;
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
    return 'light';
  },
  setTheme(theme) {
    localStorage.setItem(this.STORAGE_KEY, theme);
    this.applyTheme(theme);
  },
  applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
  },
  toggle() {
    const current = document.documentElement.getAttribute('data-theme');
    this.setTheme(current === 'dark' ? 'light' : 'dark');
  },
  watchSystemPreference() {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
      if (!localStorage.getItem(this.STORAGE_KEY)) {
        this.applyTheme(e.matches ? 'dark' : 'light');
      }
    });
  }
};
document.addEventListener('DOMContentLoaded', () => ThemeManager.init());
window.ThemeManager = ThemeManager;
