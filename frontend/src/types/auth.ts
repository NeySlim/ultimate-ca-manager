/**
 * Authentication Types
 */

export type AuthMethod = 'mtls' | 'webauthn' | 'session' | 'jwt' | 'apikey';

export type AuthState = 
  | 'checking'
  | 'mtls_detected'
  | 'webauthn_available'
  | 'password_required'
  | 'authenticating'
  | 'authenticated'
  | 'failed';

export interface User {
  id: number;
  username: string;
  email?: string;
  full_name?: string;
  roles?: string[];
  permissions?: string[];
  created_at?: string;
}

export interface AuthContext {
  user: User | null;
  authMethod: AuthMethod | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  authState: AuthState;
  login: (username: string, password: string, rememberMe?: boolean) => Promise<void>;
  loginWithWebAuthn: () => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  resetIdentity: () => void;
}

export interface LoginCredentials {
  username: string;
  password: string;
  remember_me?: boolean;
}

export interface AuthResponse {
  message: string;
  auth_method: AuthMethod;
  user?: User;
  token?: string;
}
