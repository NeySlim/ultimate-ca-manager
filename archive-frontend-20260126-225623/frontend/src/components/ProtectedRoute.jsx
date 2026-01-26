import { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router';
import { authApi } from '../services/api/authApi';

/**
 * ProtectedRoute Component
 * Verifies authentication before rendering children
 * Shows loading state during auth check
 * Redirects to login if not authenticated
 */
export function ProtectedRoute({ children }) {
  const [isChecking, setIsChecking] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const checkAuth = async () => {
      try {
        await authApi.verify();
        setIsAuthenticated(true);
      } catch (error) {
        setIsAuthenticated(false);
      } finally {
        setIsChecking(false);
      }
    };

    checkAuth();
  }, []);

  // Show loading spinner while checking auth
  if (isChecking) {
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
          <div>Verifying authentication...</div>
        </div>
      </div>
    );
  }

  // Redirect to login if not authenticated, preserving intended destination
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Render protected content
  return children;
}
