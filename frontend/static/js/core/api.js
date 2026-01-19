/**
 * API Client
 * Handles communication with UCM Backend
 */
const API = {
  baseUrl: document.querySelector('base')?.href || '/',
  apiUrl: (document.querySelector('base')?.href || '/') + 'api/',

  async request(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : this.apiUrl + endpoint;
    
    const defaultHeaders = {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    };

    const config = {
      ...options,
      headers: { ...defaultHeaders, ...options.headers }
    };

    try {
      const response = await fetch(url, config);
      
      if (response.status === 401) {
        // Unauthorized - redirect to login if not already there
        if (!window.location.pathname.includes('/login')) {
          window.location.href = 'login';
        }
        throw new Error('Unauthorized');
      }

      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.message || data.error || 'API Request Failed');
      }
      
      return data;
    } catch (error) {
      console.error('API Error:', error);
      throw error;
    }
  },

  get(endpoint) {
    return this.request(endpoint, { method: 'GET' });
  },

  post(endpoint, body) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(body)
    });
  },

  put(endpoint, body) {
    return this.request(endpoint, {
      method: 'PUT',
      body: JSON.stringify(body)
    });
  },

  delete(endpoint) {
    return this.request(endpoint, { method: 'DELETE' });
  },

  // Auth methods
  auth: {
    login: async (username, password) => {
      // Note: Backend seems to use /api/auth/login or similar. 
      // Checking api/v2 routes might be needed.
      // Assuming standard JWT login flow based on app.py
      return API.post('auth/login', { username, password });
    },
    logout: async () => {
      // Clear local storage if any
      localStorage.removeItem('ucm-token'); // If we were using manual token storage
      window.location.href = 'login';
    }
  },

  // Data methods
  certs: {
    list: () => API.get('certificates'),
    stats: () => API.get('stats') // Hypothetical endpoint
  }
};

window.API = API;
