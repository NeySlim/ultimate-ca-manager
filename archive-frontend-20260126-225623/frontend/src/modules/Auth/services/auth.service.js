import { api } from '../../../core/api/client';

export const AuthService = {
  login: async (username, password) => {
    // For MVP/Demo: Mock success if endpoint doesn't exist yet
    try {
        return await api.post('/auth/login', { username, password });
    } catch (e) {
        // Fallback for demo without backend
        if (username === 'admin' && password === 'admin') {
            return { token: 'mock-token', user: { name: 'Admin', role: 'admin' } };
        }
        throw e;
    }
  },
  
  logout: async () => {
    return await api.post('/auth/logout');
  },
  
  checkSession: async () => {
    return await api.get('/auth/session');
  }
};
