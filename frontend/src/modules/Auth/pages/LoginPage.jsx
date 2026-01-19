import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, User, Lock, Eye, EyeSlash, SignIn, Info, WarningCircle, CheckCircle } from '@phosphor-icons/react';
import { useAuth } from '../../../core/context/AuthContext';
import './../auth.css';

const LoginPage = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [step, setStep] = useState('checking'); // checking | login
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  
  // Simulation of initial check (mTLS / WebAuthn)
  useEffect(() => {
    const timer = setTimeout(() => {
      setStep('login');
    }, 1000);
    return () => clearTimeout(timer);
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
    // If success, AuthContext handles navigation
  };

  return (
    <div className="login-wrapper">
      <div className="login-container">
        <div className="login-header">
          <div className="login-logo">
            <ShieldCheck weight="duotone" className="icon-gradient" size={64} />
          </div>
          <h1 className="login-title">UCM Login</h1>
          <p className="login-subtitle">Ultimate Certificate Manager</p>
        </div>

        <div className="login-card">
          {step === 'checking' && (
             <div className="auth-method active">
                <div className="auth-status">
                    <div className="auth-status-icon">
                        <div className="spinner"></div>
                    </div>
                    <div className="auth-status-text">Checking authentication...</div>
                    <div className="auth-status-subtext">Trying certificate-based login</div>
                </div>
                
                <div className="info-box">
                    <div className="info-box-icon"><Info size={16} weight="bold" /></div>
                    <div>
                        Attempting automatic authentication via client certificate (mTLS).
                    </div>
                </div>
            </div>
          )}

          {step === 'login' && (
            <div className="auth-method active">
                {error && (
                  <div style={{ 
                      background: '#2e1e1e', 
                      border: '1px solid #4a2d2d', 
                      borderRadius: '3px', 
                      padding: '12px', 
                      marginBottom: '16px', 
                      display: 'flex', 
                      gap: '10px', 
                      color: '#e57373', 
                      fontSize: '13px',
                      alignItems: 'center'
                  }}>
                    <WarningCircle size={16} weight="bold" />
                    {error}
                  </div>
                )}

                <form onSubmit={handleLogin}>
                    <div className="form-group">
                        <label className="form-label" htmlFor="username">Username</label>
                        <div className="input-group">
                            <span className="input-icon"><User weight="duotone" /></span>
                            <input 
                                type="text" 
                                name="username"
                                id="username" 
                                className="form-input" 
                                placeholder="Enter your username"
                                required
                            />
                        </div>
                    </div>

                    <div className="form-group">
                        <label className="form-label" htmlFor="password">Password</label>
                        <div className="input-group">
                            <span className="input-icon"><Lock weight="duotone" /></span>
                            <input 
                                type={showPassword ? "text" : "password"} 
                                name="password"
                                id="password" 
                                className="form-input" 
                                placeholder="Enter your password"
                                required
                            />
                            <button 
                                type="button" 
                                className="input-action" 
                                onClick={() => setShowPassword(!showPassword)}
                            >
                                {showPassword ? <EyeSlash /> : <Eye />}
                            </button>
                        </div>
                    </div>

                    <div className="form-checkbox-group">
                        <input type="checkbox" id="remember" style={{ accentColor: '#5a8fc7' }} />
                        <label htmlFor="remember" style={{ fontSize: '13px', color: '#ccc' }}>Remember me</label>
                    </div>

                    <button type="submit" className="btn btn-primary" disabled={loading}>
                        {loading ? <div className="spinner" style={{ width: '16px', height: '16px', borderTopColor: 'white' }}></div> : <SignIn weight="bold" />}
                        {loading ? 'Signing In...' : 'Sign In'}
                    </button>
                </form>

                <div className="divider">
                    <div className="divider-line"></div>
                    <div className="divider-text">Or continue with</div>
                    <div className="divider-line"></div>
                </div>

                <button className="btn" onClick={() => alert('WebAuthn not implemented in demo')}>
                    <ShieldCheck weight="duotone" size={18} />
                    Security Key (WebAuthn)
                </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
