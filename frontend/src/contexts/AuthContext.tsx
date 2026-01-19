/**
 * Authentication Context Provider
 * Handles progressive auth flow: mTLS → WebAuthn → Password
 */

import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import type { AuthContext as IAuthContext, AuthState, User, AuthMethod } from '../types/auth';
import { notifications } from '@mantine/notifications';

const AuthContext = createContext<IAuthContext | undefined>(undefined);

const STORAGE_KEYS = {
  REMEMBER_ME: 'ucm-remember-me',
  STORED_USERNAME: 'ucm-username',
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [authMethod, setAuthMethod] = useState<AuthMethod | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authState, setAuthState] = useState<AuthState>('checking');

  // Check for stored remember me
  const getRememberedUsername = () => {
    const rememberMe = localStorage.getItem(STORAGE_KEYS.REMEMBER_ME) === 'true';
    return rememberMe ? localStorage.getItem(STORAGE_KEYS.STORED_USERNAME) : null;
  };

  // Reset stored identity
  const resetIdentity = useCallback(() => {
    localStorage.removeItem(STORAGE_KEYS.REMEMBER_ME);
    localStorage.removeItem(STORAGE_KEYS.STORED_USERNAME);
    setAuthState('password_required');
    notifications.show({
      title: 'Identity cleared',
      message: 'Please sign in again',
      color: 'blue',
    });
  }, []);

  // Progressive auth check
  const checkAuth = useCallback(async () => {
    setIsLoading(true);
    setAuthState('checking');

    try {
      // Step 1: Try session verification (covers mTLS and existing sessions)
      const verifyResponse = await fetch('/api/auth/verify', {
        credentials: 'include',
      });

      if (verifyResponse.ok) {
        const data = await verifyResponse.json();
        if (data.authenticated) {
          setUser(data.user);
          setAuthMethod(data.auth_method);
          setAuthState('authenticated');
          setIsLoading(false);
          return;
        }
      }

      // Step 2: Check if WebAuthn is available and registered
      const rememberedUsername = getRememberedUsername();
      if (rememberedUsername && window.PublicKeyCredential) {
        setAuthState('webauthn_available');
        setIsLoading(false);
        return;
      }

      // Step 3: Show password form
      setAuthState('password_required');
      setIsLoading(false);
    } catch (error) {
      console.error('Auth check failed:', error);
      setAuthState('password_required');
      setIsLoading(false);
    }
  }, []);

  // Login with password
  const login = useCallback(async (username: string, password: string, rememberMe?: boolean) => {
    setAuthState('authenticating');

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Login failed');
      }

      setUser(data.user || { id: 0, username });
      setAuthMethod(data.auth_method || 'session');
      setAuthState('authenticated');

      // Store remember me
      if (rememberMe) {
        localStorage.setItem(STORAGE_KEYS.REMEMBER_ME, 'true');
        localStorage.setItem(STORAGE_KEYS.STORED_USERNAME, username);
      } else {
        localStorage.removeItem(STORAGE_KEYS.REMEMBER_ME);
        localStorage.removeItem(STORAGE_KEYS.STORED_USERNAME);
      }

      notifications.show({
        title: 'Welcome back!',
        message: `Logged in as ${username}`,
        color: 'green',
      });
    } catch (error) {
      setAuthState('failed');
      setTimeout(() => setAuthState('password_required'), 2000);
      
      notifications.show({
        title: 'Login failed',
        message: error instanceof Error ? error.message : 'Invalid credentials',
        color: 'red',
      });
      
      throw error;
    }
  }, []);

  // Login with WebAuthn
  const loginWithWebAuthn = useCallback(async () => {
    setAuthState('authenticating');

    try {
      const username = getRememberedUsername();
      if (!username) {
        throw new Error('No stored username for WebAuthn');
      }

      // TODO: Implement actual WebAuthn flow
      // For now, just show not implemented
      notifications.show({
        title: 'WebAuthn',
        message: 'WebAuthn login not yet implemented',
        color: 'yellow',
      });

      setAuthState('password_required');
    } catch (error) {
      setAuthState('failed');
      setTimeout(() => setAuthState('password_required'), 2000);
      
      notifications.show({
        title: 'WebAuthn failed',
        message: error instanceof Error ? error.message : 'Please use password',
        color: 'red',
      });
      
      throw error;
    }
  }, []);

  // Logout
  const logout = useCallback(async () => {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
      });

      setUser(null);
      setAuthMethod(null);
      setAuthState('password_required');

      notifications.show({
        title: 'Logged out',
        message: 'See you soon!',
        color: 'blue',
      });
    } catch (error) {
      console.error('Logout failed:', error);
    }
  }, []);

  // Initial auth check
  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  return (
    <AuthContext.Provider
      value={{
        user,
        authMethod,
        isAuthenticated: authState === 'authenticated',
        isLoading,
        authState,
        login,
        loginWithWebAuthn,
        logout,
        checkAuth,
        resetIdentity,
      }}
    >
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
