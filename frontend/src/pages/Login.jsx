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
          <div className={styles.loginLogo}>
            <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
              <rect width="64" height="64" rx="12" fill="url(#logo-gradient)" />
              <path
                d="M32 16L44 24V40L32 48L20 40V24L32 16Z"
                stroke="white"
                strokeWidth="2"
                strokeLinejoin="round"
              />
              <circle cx="32" cy="32" r="4" fill="white" />
              <defs>
                <linearGradient id="logo-gradient" x1="0" y1="0" x2="64" y2="64">
                  <stop offset="0%" stopColor="var(--accent-gradient-start)" />
                  <stop offset="100%" stopColor="var(--accent-gradient-end)" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h1 className={styles.loginTitle}>Unified Certificate Manager</h1>
          <p className={styles.loginSubtitle}>Sign in to manage your PKI infrastructure</p>
        </div>

        <form className={styles.loginForm} onSubmit={handleSubmit}>
          <Input
            label="Username"
            placeholder="Enter your username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            required
          />

          <PasswordInput
            label="Password"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
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
