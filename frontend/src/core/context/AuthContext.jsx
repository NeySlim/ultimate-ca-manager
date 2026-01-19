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
      await api.get('/auth/verify', { redirectOn401: false });
      setIsAuthenticated(true);
      // Ensure local storage matches backend state
      localStorage.setItem('ucm-auth', 'true');
    } catch (error) {
      console.log('Not authenticated');
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
