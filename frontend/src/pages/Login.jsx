import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Input, PasswordInput } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import styles from './Login.module.css';

/**
 * Login Page
 * Standalone authentication page (not in AppLayout)
 */
export function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    // Simulate login (TODO: Replace with real API call)
    setTimeout(() => {
      setLoading(false);
      // For now, just redirect to dashboard
      navigate('/dashboard');
    }, 500);
  };

  return (
    <div className={styles.loginPage}>
      <div className={styles.loginContainer}>
        <div className={styles.loginHeader}>
          <svg className={styles.loginLogo} width="64" height="64" viewBox="0 0 192 150" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="ucm-logo-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style={{ stopColor: 'var(--accent-gradient-start)', stopOpacity: 1 }} />
                <stop offset="100%" style={{ stopColor: 'var(--accent-gradient-end)', stopOpacity: 1 }} />
              </linearGradient>
            </defs>
            <rect x="8" y="0" width="176" height="116" rx="4" fill="url(#ucm-logo-gradient)"/>
            <rect x="12" y="4" width="168" height="108" rx="3" fill="transparent"/>
            <line x1="42" y1="22" x2="150" y2="22" stroke="url(#ucm-logo-gradient)" strokeWidth="4" opacity="0.3"/>
            <line x1="42" y1="34" x2="138" y2="34" stroke="url(#ucm-logo-gradient)" strokeWidth="4" opacity="0.3"/>
            <line x1="42" y1="46" x2="126" y2="46" stroke="url(#ucm-logo-gradient)" strokeWidth="4" opacity="0.3"/>
            <circle cx="96" cy="70" r="24" fill="url(#ucm-logo-gradient)"/>
            <circle cx="96" cy="70" r="20" fill="none" stroke="#fff" strokeWidth="3"/>
            <circle cx="96" cy="70" r="16" fill="none" stroke="#fff" strokeWidth="2" opacity="0.5"/>
            <path d="M88 70l5 5 11-11" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M70 116 L70 142 L80 133 L80 116 Z" fill="url(#ucm-logo-gradient)"/>
            <path d="M70 116 L70 142 L80 133 L80 116" fill="none" stroke="#fff" strokeWidth="2" opacity="0.6"/>
            <path d="M112 116 L112 142 L102 133 L102 116 Z" fill="url(#ucm-logo-gradient)"/>
            <path d="M112 116 L112 142 L102 133 L102 116" fill="none" stroke="#fff" strokeWidth="2" opacity="0.6"/>
          </svg>
          <h1 className={styles.loginTitle}>Unified Certificate Manager</h1>
          <p className={styles.loginSubtitle}>Sign in to manage your PKI infrastructure</p>
        </div>

        <form className={styles.loginForm} onSubmit={handleSubmit}>
          <Input
            label="Username"
            placeholder="Enter your username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />

          <PasswordInput
            label="Password"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />

          <div className={styles.loginOptions}>
            <label className={styles.checkbox}>
              <input type="checkbox" />
              <span>Remember me</span>
            </label>
            <a href="#" className={styles.forgotPassword}>
              Forgot password?
            </a>
          </div>

          <Button
            type="submit"
            variant="primary"
            className={styles.loginButton}
            disabled={loading || !username || !password}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </Button>
        </form>

        <div className={styles.loginFooter}>
          <p className={styles.version}>UCM v2.1.0</p>
        </div>
      </div>
    </div>
  );
}

export default Login;
