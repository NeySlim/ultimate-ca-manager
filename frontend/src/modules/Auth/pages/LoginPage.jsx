import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, Certificate, Key, Users, CheckCircle, User, Lock, Eye, EyeSlash, SignIn } from '@phosphor-icons/react';
import { useAuth } from '../../../core/context/AuthContext';
import { Button, Input, PasswordInput, Text } from '../../../components/ui';
import './../auth.css';

const LoginPage = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [step, setStep] = useState('checking'); // checking | login
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [stats, setStats] = useState({
    cas: '—',
    certs: '—',
    acme: '—',
    users: '—'
  });
  
  // Initial authentication check
  useEffect(() => {
    let mounted = true;

    const checkStatus = async () => {
      try {
        await new Promise(r => setTimeout(r, 800));
        
        const response = await fetch('/api/auth/verify', { 
            headers: { 'Accept': 'application/json' }
        });
        
        if (response.ok) {
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                const data = await response.json();
                if (data.authenticated && mounted) {
                    window.location.href = '/'; 
                    return;
                }
            }
        }
      } catch (e) {
        console.error("Auth check failed", e);
      }
      
      if (mounted) {
        setStep('login');
      }
    };

    // Fetch stats for sidebar
    const fetchStats = async () => {
      try {
        const res = await fetch('/api/v2/stats/overview');
        if (res.ok) {
          const response = await res.json();
          const data = response.data; // API wraps in {data: {...}}
          setStats({
            cas: data.total_cas || '—',
            certs: data.total_certs || '—',
            acme: data.acme_accounts || '—',
            users: data.active_users || '—'
          });
        }
      } catch (e) {
        console.error('Stats fetch failed', e);
      }
    };

    checkStatus();
    fetchStats();

    return () => { mounted = false; };
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    const username = e.target.username.value;
    const password = e.target.password.value;

    const success = await login(username, password);
    
    if (!success) {
         setError('Invalid credentials or server error');
         setLoading(false);
    }
  };

  return (
    <div className="login-wrapper-v2">
      {/* Left Sidebar - Stats & Info */}
      <div className="login-sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <ShieldCheck weight="duotone" size={28} style={{ color: 'white' }} />
          </div>
          <div className="sidebar-title">
            <h1>Ultimate CA Manager</h1>
            <Text size="sm" color="secondary">Enterprise Certificate Authority</Text>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="stats-grid">
          <div className="stat-card">
            <Text size="xs" color="tertiary" transform="uppercase" className="stat-label">
              Certificate Authorities
            </Text>
            <div className="stat-value">
              <Certificate size={24} className="stat-icon icon-gradient" />
              <span>{stats.cas}</span>
            </div>
          </div>

          <div className="stat-card">
            <Text size="xs" color="tertiary" transform="uppercase" className="stat-label">
              Certificates
            </Text>
            <div className="stat-value">
              <ShieldCheck size={24} className="stat-icon icon-gradient" />
              <span>{stats.certs}</span>
            </div>
          </div>

          <div className="stat-card">
            <Text size="xs" color="tertiary" transform="uppercase" className="stat-label">
              ACME Accounts
            </Text>
            <div className="stat-value">
              <Key size={24} className="stat-icon icon-gradient" />
              <span>{stats.acme}</span>
            </div>
          </div>

          <div className="stat-card">
            <Text size="xs" color="tertiary" transform="uppercase" className="stat-label">
              Active Users
            </Text>
            <div className="stat-value">
              <Users size={24} className="stat-icon icon-gradient" />
              <span>{stats.users}</span>
            </div>
          </div>
        </div>

        {/* System Status */}
        <div className="system-status">
          <div className="status-header">
            <span className="status-indicator"></span>
            <Text size="sm" weight={600}>System Status</Text>
          </div>
          <div className="status-list">
            <div className="status-item">
              <Text size="xs" color="tertiary">Platform</Text>
              <Text size="xs" color="primary">Operational</Text>
            </div>
            <div className="status-item">
              <Text size="xs" color="tertiary">Database</Text>
              <Text size="xs" color="primary">Healthy</Text>
            </div>
            <div className="status-item">
              <Text size="xs" color="tertiary">ACME Service</Text>
              <Text size="xs" color="primary">Active</Text>
            </div>
          </div>
        </div>

        <div className="sidebar-footer">
          <Text size="xs" color="tertiary">
            <ShieldCheck size={14} weight="fill" style={{ marginRight: 4, verticalAlign: 'middle' }} />
            Secured by UCM v2.0
          </Text>
        </div>
      </div>

      {/* Right Side - Login Form */}
      <div className="login-main">
        <div className="login-card-v2">
          {step === 'checking' && (
            <div className="auth-checking">
              <div className="spinner-large"></div>
              <Text size="md" weight={600}>Checking authentication...</Text>
              <Text size="sm" color="secondary">Trying certificate-based login</Text>
            </div>
          )}

          {step === 'login' && (
            <>
              <div className="login-header-v2">
                <h2>Welcome Back</h2>
                <Text size="sm" color="secondary">Sign in to your account</Text>
              </div>

              {error && (
                <div className="alert alert-error">
                  <div className="alert-content">
                    <div className="alert-message">{error}</div>
                  </div>
                </div>
              )}

              <form onSubmit={handleLogin} className="login-form">
                <Input
                  label="Username"
                  name="username"
                  type="text"
                  placeholder="Enter your username"
                  required
                />

                <PasswordInput
                  label="Password"
                  name="password"
                  placeholder="Enter your password"
                  required
                />

                <div className="form-checkbox">
                  <input type="checkbox" id="remember" />
                  <label htmlFor="remember">
                    <Text size="sm" color="secondary">Remember me</Text>
                  </label>
                </div>

                <Button 
                  type="submit" 
                  variant="primary" 
                  disabled={loading}
                  style={{ width: '100%', marginTop: '8px' }}
                >
                  {loading ? 'Signing In...' : 'Sign In'}
                </Button>
              </form>

              <div className="login-divider">
                <span>Or continue with</span>
              </div>

              <Button 
                variant="default"
                style={{ width: '100%' }}
                onClick={() => alert('WebAuthn not implemented in demo')}
              >
                <ShieldCheck size={18} weight="duotone" style={{ marginRight: 8 }} />
                Security Key (WebAuthn)
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
