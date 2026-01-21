import { useState, useEffect } from 'react';
import { getTheme, getAccent, setTheme, setAccent, THEMES, ACCENTS } from '../../theme/theme';
import styles from './ThemePicker.module.css';

/**
 * ThemePicker Component
 * 
 * Allows users to:
 * - Toggle between dark and light themes
 * - Choose from 6 accent colors (blue, green, purple, orange, red, cyan)
 * 
 * Theme state persisted in localStorage
 * Updates HTML attributes: data-theme, data-accent
 */
export function ThemePicker() {
  const [currentTheme, setCurrentTheme] = useState(getTheme());
  const [currentAccent, setCurrentAccent] = useState(getAccent());
  const [isOpen, setIsOpen] = useState(false);

  const handleThemeChange = (theme) => {
    setTheme(theme);
    setCurrentTheme(theme);
  };

  const handleAccentChange = (accent) => {
    setAccent(accent);
    setCurrentAccent(accent);
  };

  // Accent color metadata
  const accentColors = {
    blue: { label: 'Blue', color: '#5a8fc7' },
    green: { label: 'Green', color: '#81c784' },
    purple: { label: 'Purple', color: '#ba68c8' },
    orange: { label: 'Orange', color: '#ffb74d' },
    red: { label: 'Red', color: '#e57373' },
    cyan: { label: 'Cyan', color: '#4dd0e1' },
  };

  return (
    <div className={styles.themePicker}>
      <button
        className={styles.triggerButton}
        onClick={() => setIsOpen(!isOpen)}
        title="Change theme"
      >
        <i className="ph ph-palette" />
      </button>

      {isOpen && (
        <>
          <div className={styles.overlay} onClick={() => setIsOpen(false)} />
          
          <div className={styles.panel}>
            <div className={styles.header}>
              <h3 className={styles.title}>Theme Settings</h3>
              <button
                className={styles.closeButton}
                onClick={() => setIsOpen(false)}
              >
                <i className="ph ph-x" />
              </button>
            </div>

            <div className={styles.body}>
              {/* Theme Toggle (Dark / Light) */}
              <div className={styles.section}>
                <label className={styles.label}>Theme</label>
                <div className={styles.themeToggle}>
                  <button
                    className={`${styles.themeButton} ${currentTheme === 'dark' ? styles.active : ''}`}
                    onClick={() => handleThemeChange('dark')}
                  >
                    <i className="ph ph-moon" />
                    <span>Dark</span>
                  </button>
                  <button
                    className={`${styles.themeButton} ${currentTheme === 'light' ? styles.active : ''}`}
                    onClick={() => handleThemeChange('light')}
                  >
                    <i className="ph ph-sun" />
                    <span>Light</span>
                  </button>
                </div>
              </div>

              {/* Accent Color Grid (3×2) */}
              <div className={styles.section}>
                <label className={styles.label}>Accent Color</label>
                <div className={styles.accentGrid}>
                  {ACCENTS.map((accent) => (
                    <button
                      key={accent}
                      className={`${styles.accentButton} ${currentAccent === accent ? styles.active : ''}`}
                      onClick={() => handleAccentChange(accent)}
                      title={accentColors[accent].label}
                      style={{ '--accent-preview': accentColors[accent].color }}
                    >
                      <span 
                        className={styles.accentSwatch}
                        style={{ background: accentColors[accent].color }}
                      />
                      <span className={styles.accentLabel}>
                        {accentColors[accent].label}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default ThemePicker;
