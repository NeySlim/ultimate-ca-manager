import React, { createContext, useContext, useState, useEffect } from 'react';
import { useNavigate, useLocation, Navigate } from 'react-router-dom';
import { api } from '../api/client';

const AuthContext = createContext(null);

export const useAuth = () => {
  return useContext(AuthContext);
};

export const AuthProvider = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      // Don't redirect on 401 during initial check
      // Note: client.js prepends /api, so this becomes /api/auth/verify
      const response = await api.get('/auth/verify', { redirectOn401: false });
      
      // Determine response structure
      let authData = null;
      
      // Case 1: Response is the data object directly
      if (response && response.authenticated !== undefined) {
          authData = response;
      }
      // Case 2: Response is wrapped in { data: ... }
      else if (response && response.data && response.data.authenticated !== undefined) {
          authData = response.data;
      }
      // Case 3: Response is { user: ... } legacy format
      else if (response && response.user) {
          authData = { authenticated: true, user: response.user };
      }

      if (authData) {
          if (authData.authenticated) {
              setIsAuthenticated(true);
              localStorage.setItem('ucm-auth', 'true');
          } else {
              console.log('Auth check: Not authenticated');
              setIsAuthenticated(false);
              localStorage.removeItem('ucm-auth');
          }
      } else {
          console.log('Auth check: Unknown response format', response);
          setIsAuthenticated(false);
          localStorage.removeItem('ucm-auth');
      }
    } catch (error) {
      console.log('Not authenticated (error)', error);
      setIsAuthenticated(false);
      localStorage.removeItem('ucm-auth');
    } finally {
      setIsLoading(false);
    }
  };

  const login = async (username, password) => {
    try {
      await api.post('/auth/login', { username, password });
      setIsAuthenticated(true);
      localStorage.setItem('ucm-auth', 'true');
      
      // Navigate to origin or dashboard
      const origin = location.state?.from?.pathname || '/';
      navigate(origin);
      return true;
    } catch (error) {
      console.error('Login failed:', error);
      return false;
    }
  };

  const logout = async () => {
    try {
      await api.post('/auth/logout');
    } catch (e) {
      console.warn('Logout API call failed', e);
    }
    localStorage.removeItem('ucm-auth');
    setIsAuthenticated(false);
    navigate('/login');
  };

  const value = {
    isAuthenticated,
    isLoading,
    login,
    logout
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const RequireAuth = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <div>Loading Auth...</div>; // Or a proper loading spinner
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
};
