// Theme Manager - Simple & Persistent
class ThemeManager {
  constructor() {
    this.current = this.getStoredTheme() || 'dark';
    this.apply(this.current);
  }

  getStoredTheme() {
    return localStorage.getItem('theme');
  }

  setStoredTheme(theme) {
    localStorage.setItem('theme', theme);
  }

  apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    this.current = theme;
    this.setStoredTheme(theme);
  }

  toggle() {
    const newTheme = this.current === 'dark' ? 'light' : 'dark';
    this.apply(newTheme);
    return newTheme;
  }

  isDark() {
    return this.current === 'dark';
  }

  isLight() {
    return this.current === 'light';
  }
}

// Export singleton
const theme = new ThemeManager();

if (typeof window !== 'undefined') {
  window.theme = theme;
}
