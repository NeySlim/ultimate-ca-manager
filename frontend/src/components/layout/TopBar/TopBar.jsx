import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { 
  Moon, 
  Sun,
  GridFour,
  PencilSimple,
  DownloadSimple,
  Plus,
  CaretDown
} from '@phosphor-icons/react';
import { useTheme } from '../../../contexts/ThemeContext';
import './TopBar.css';

const THEMES = [
  { name: 'Blue Sky', primary: '#5a8fc7', secondary: '#7aa5d9' },
  { name: 'Purple Dream', primary: '#9985c7', secondary: '#b5a3d9' },
  { name: 'Mint Fresh', primary: '#5eb89b', secondary: '#7bc9af' },
  { name: 'Amber Warm', primary: '#c99652', secondary: '#d9ac73' },
  { name: 'Mokka', primary: '#b8926d', secondary: '#c9a687' },
  { name: 'Pink Soft', primary: '#c77799', secondary: '#d994ad' },
];

const ThemeSelector = () => {
  const { accentColor, setAccentColor } = useTheme();
  const [isOpen, setIsOpen] = useState(false);

  const handleThemeSelect = (theme) => {
    setAccentColor(theme.primary);
    setIsOpen(false);
  };

  const currentTheme = THEMES.find(t => t.primary === accentColor) || THEMES[0];

  return (
    <div className="theme-selector">
      <button className="theme-selector-btn" onClick={() => setIsOpen(!isOpen)}>
        <div 
          className="theme-color-preview" 
          style={{ background: `linear-gradient(135deg, ${currentTheme.primary}, ${currentTheme.secondary})` }}
        />
        <span>Theme</span>
        <CaretDown size={10} />
      </button>
      {isOpen && (
        <div className="theme-dropdown">
          {THEMES.map(theme => (
            <div 
              key={theme.name}
              className={`theme-option ${theme.primary === accentColor ? 'selected' : ''}`}
              onClick={() => handleThemeSelect(theme)}
            >
              <div 
                className="theme-preview" 
                style={{ background: `linear-gradient(135deg, ${theme.primary}, ${theme.secondary})` }}
              />
              <div className="theme-info">
                <div className="theme-name">{theme.name}</div>
                <div className="theme-hex">{theme.primary}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const getPageTitle = (pathname) => {
  const routes = {
    '/': 'Dashboard',
    '/cas': 'Certificate Authorities',
    '/certificates': 'Certificates',
    '/csrs': 'Certificate Requests',
    '/templates': 'Templates',
    '/acme': 'ACME Protocol',
    '/scep': 'SCEP Server',
    '/crl': 'CRL & OCSP',
    '/import': 'Import',
    '/truststore': 'Trust Store',
    '/users': 'Users',
    '/activity': 'Activity Log',
    '/settings': 'Settings',
  };
  return routes[pathname] || 'Dashboard';
};

const TopBar = () => {
  const { colorScheme, setColorScheme } = useTheme();
  const location = useLocation();

  const toggleColorScheme = () => {
    setColorScheme(colorScheme === 'dark' ? 'light' : 'dark');
  };

  return (
    <div className="topbar">
      {/* LEFT: Page Title */}
      <div className="topbar-left">
        <div className="page-title">{getPageTitle(location.pathname)}</div>
      </div>

      {/* RIGHT: Actions */}
      <div className="topbar-right">
        <button className="btn" title="Show/hide 12-column grid">
          <GridFour size={16} />
          Grid
        </button>

        <ThemeSelector />

        <button className="btn" onClick={toggleColorScheme} title="Toggle dark/light mode">
          {colorScheme === 'dark' ? <Moon size={16} /> : <Sun size={16} />}
        </button>

        <button className="btn">
          <PencilSimple size={16} />
          Edit Layout
        </button>

        <button className="btn">
          <DownloadSimple size={16} />
          Export
        </button>

        <button className="btn btn-primary">
          <Plus size={16} className="icon-gradient" />
          Quick Issue
        </button>
      </div>
    </div>
  );
};

export default TopBar;
