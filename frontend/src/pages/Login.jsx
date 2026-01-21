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
          <svg className={styles.loginLogo} width="60" height="40" viewBox="0 0 60 40" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="chain-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style={{ stopColor: 'var(--accent-gradient-start)', stopOpacity: 1 }} />
                <stop offset="100%" style={{ stopColor: 'var(--accent-gradient-end)', stopOpacity: 1 }} />
              </linearGradient>
            </defs>
            <rect x="4" y="8" width="12" height="20" rx="6" fill="none" stroke="url(#chain-gradient)" strokeWidth="3"/>
            <rect x="24" y="16" width="12" height="20" rx="6" fill="none" stroke="url(#chain-gradient)" strokeWidth="3"/>
            <rect x="44" y="4" width="12" height="20" rx="6" fill="none" stroke="url(#chain-gradient)" strokeWidth="3"/>
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
