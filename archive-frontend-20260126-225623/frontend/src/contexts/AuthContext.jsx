import { createContext, useContext, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { authApi } from '../services/api/authApi';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    // Skip auth check on login page
    if (location.pathname === '/login') {
      setIsLoading(false);
      return;
    }

    try {
      await authApi.verify();
      setIsAuthenticated(true);
    } catch (error) {
      setIsAuthenticated(false);
      navigate('/login', { replace: true });
    } finally {
      setIsLoading(false);
    }
  };

  const login = () => {
    setIsAuthenticated(true);
  };

  const logout = () => {
    setIsAuthenticated(false);
    navigate('/login', { replace: true });
  };

  // Show loading screen while checking auth (BLOCKS everything)
  if (isLoading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        backgroundColor: 'var(--bg-primary)',
        color: 'var(--text-tertiary)',
      }}>
        <div style={{ textAlign: 'center' }}>
          <i className="ph ph-spinner" style={{ 
            fontSize: '48px', 
            marginBottom: '16px',
            animation: 'spin 1s linear infinite' 
          }} />
          <div>Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
