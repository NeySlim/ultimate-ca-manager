import { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router';
import styles from './CommandPalette.module.css';
import { MagnifyingGlass, ArrowRight, Clock, Hash } from '@phosphor-icons/react';

// Command categories
const COMMANDS = [
  // Navigation
  { id: 'nav-dashboard', label: 'Go to Dashboard', category: 'Navigation', path: '/dashboard', icon: '📊', keywords: ['home', 'main', 'overview'] },
  { id: 'nav-cas', label: 'Go to Certificate Authorities', category: 'Navigation', path: '/cas', icon: '🏛️', keywords: ['ca', 'authorities', 'root'] },
  { id: 'nav-certificates', label: 'Go to Certificates', category: 'Navigation', path: '/certificates', icon: '📜', keywords: ['certs', 'ssl', 'tls'] },
  { id: 'nav-csrs', label: 'Go to Certificate Requests', category: 'Navigation', path: '/csrs', icon: '📝', keywords: ['csr', 'requests'] },
  { id: 'nav-templates', label: 'Go to Templates', category: 'Navigation', path: '/templates', icon: '📋', keywords: ['template', 'presets'] },
  { id: 'nav-users', label: 'Go to Users', category: 'Navigation', path: '/users', icon: '👥', keywords: ['team', 'members', 'people'] },
  { id: 'nav-settings', label: 'Go to Settings', category: 'Navigation', path: '/settings', icon: '⚙️', keywords: ['config', 'preferences'] },
  { id: 'nav-activity', label: 'Go to Activity Log', category: 'Navigation', path: '/activity', icon: '📅', keywords: ['log', 'history', 'audit'] },
  
  // Actions
  { id: 'action-new-ca', label: 'Create New CA', category: 'Actions', action: 'new-ca', icon: '➕', keywords: ['new', 'add', 'create', 'authority'] },
  { id: 'action-issue-cert', label: 'Issue Certificate', category: 'Actions', action: 'issue-cert', icon: '🎫', keywords: ['new', 'create', 'issue', 'certificate'] },
  { id: 'action-import-ca', label: 'Import CA', category: 'Actions', action: 'import-ca', icon: '📥', keywords: ['upload', 'import'] },
  { id: 'action-export-ca', label: 'Export CA', category: 'Actions', action: 'export-ca', icon: '📤', keywords: ['download', 'export'] },
  { id: 'action-backup', label: 'Create Backup', category: 'Actions', action: 'backup', icon: '💾', keywords: ['backup', 'save', 'download'] },
  
  // Settings
  { id: 'setting-theme', label: 'Change Theme', category: 'Settings', action: 'theme', icon: '🎨', keywords: ['dark', 'light', 'theme', 'color'] },
  { id: 'setting-acme', label: 'ACME Settings', category: 'Settings', path: '/settings?tab=acme', icon: '🔐', keywords: ['acme', 'letsencrypt'] },
  { id: 'setting-scep', label: 'SCEP Settings', category: 'Settings', path: '/settings?tab=scep', icon: '🔑', keywords: ['scep', 'enrollment'] },
  { id: 'setting-crl', label: 'CRL Settings', category: 'Settings', path: '/settings?tab=crl', icon: '🚫', keywords: ['crl', 'revocation'] },
  { id: 'setting-backup', label: 'Backup & Restore', category: 'Settings', path: '/settings?tab=backup', icon: '🗄️', keywords: ['backup', 'restore'] },
];

// Fuzzy search function
function fuzzyMatch(str, pattern) {
  const patternLower = pattern.toLowerCase();
  const strLower = str.toLowerCase();
  
  let patternIdx = 0;
  let score = 0;
  let consecutiveMatches = 0;
  
  for (let i = 0; i < strLower.length; i++) {
    if (strLower[i] === patternLower[patternIdx]) {
      score += 1 + consecutiveMatches;
      consecutiveMatches++;
      patternIdx++;
      
      if (patternIdx === patternLower.length) {
        return score;
      }
    } else {
      consecutiveMatches = 0;
    }
  }
  
  return patternIdx === patternLower.length ? score : 0;
}

export function CommandPalette({ isOpen, onClose }) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [recentCommands, setRecentCommands] = useState([]);
  const inputRef = useRef(null);
  const navigate = useNavigate();

  // Filter and sort commands
  const filteredCommands = useMemo(() => {
    if (!query) {
      // Show recent commands when no query
      return recentCommands.slice(0, 5);
    }

    const results = COMMANDS.map(cmd => {
      // Search in label
      const labelScore = fuzzyMatch(cmd.label, query);
      
      // Search in keywords
      const keywordScore = cmd.keywords
        ? Math.max(...cmd.keywords.map(kw => fuzzyMatch(kw, query)))
        : 0;
      
      // Search in category
      const categoryScore = fuzzyMatch(cmd.category, query);
      
      const totalScore = Math.max(labelScore, keywordScore, categoryScore);
      
      return { ...cmd, score: totalScore };
    })
    .filter(cmd => cmd.score > 0)
    .sort((a, b) => b.score - a.score);

    return results;
  }, [query, recentCommands]);

  // Execute command
  const executeCommand = (command) => {
    // Add to recent commands
    const newRecent = [command, ...recentCommands.filter(c => c.id !== command.id)].slice(0, 10);
    setRecentCommands(newRecent);
    localStorage.setItem('ucm-recent-commands', JSON.stringify(newRecent));

    // Execute action
    if (command.path) {
      navigate(command.path);
    } else if (command.action) {
      // Dispatch custom event for actions
      window.dispatchEvent(new CustomEvent('command-palette-action', { detail: command.action }));
    }

    onClose();
  };

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isOpen) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(i => Math.min(i + 1, filteredCommands.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(i => Math.max(i - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          executeCommand(filteredCommands[selectedIndex]);
        }
      } else if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, selectedIndex, filteredCommands, onClose]);

  // Auto-focus input
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Reset on open
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
    }
  }, [isOpen]);

  // Load recent commands
  useEffect(() => {
    try {
      const stored = localStorage.getItem('ucm-recent-commands');
      if (stored) {
        setRecentCommands(JSON.parse(stored));
      }
    } catch (error) {
      console.error('Failed to load recent commands:', error);
    }
  }, []);

  if (!isOpen) return null;

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.searchBox}>
          <MagnifyingGlass size={20} className={styles.searchIcon} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command or search..."
            className={styles.searchInput}
          />
          <kbd className={styles.kbd}>ESC</kbd>
        </div>

        <div className={styles.results}>
          {filteredCommands.length === 0 && query && (
            <div className={styles.empty}>No commands found</div>
          )}

          {filteredCommands.length === 0 && !query && (
            <div className={styles.empty}>
              <Clock size={32} weight="duotone" />
              <p>No recent commands</p>
              <p className={styles.emptyHint}>Start typing to search</p>
            </div>
          )}

          {!query && recentCommands.length > 0 && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>
                <Clock size={14} /> Recent
              </div>
            </div>
          )}

          {filteredCommands.map((cmd, index) => (
            <div
              key={cmd.id}
              className={`${styles.item} ${index === selectedIndex ? styles.selected : ''}`}
              onClick={() => executeCommand(cmd)}
              onMouseEnter={() => setSelectedIndex(index)}
            >
              <span className={styles.icon}>{cmd.icon}</span>
              <div className={styles.content}>
                <div className={styles.label}>{cmd.label}</div>
                <div className={styles.category}>
                  <Hash size={12} />
                  {cmd.category}
                </div>
              </div>
              <ArrowRight size={16} className={styles.arrow} />
            </div>
          ))}
        </div>

        <div className={styles.footer}>
          <div className={styles.hint}>
            <kbd>↑↓</kbd> Navigate
            <kbd>⏎</kbd> Select
            <kbd>ESC</kbd> Close
          </div>
        </div>
      </div>
    </div>
  );
}

// Global keyboard listener hook
export function useCommandPalette() {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen(true);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return { isOpen, setIsOpen, close: () => setIsOpen(false) };
}
