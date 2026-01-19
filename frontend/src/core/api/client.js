const API_BASE = '/api';

class ApiClient {
  async request(endpoint, options = {}) {
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    // Add Auth Token if exists (Mock logic, replace with real JWT/Cookie handling if needed)
    // const token = localStorage.getItem('ucm-token');
    // if (token) config.headers.Authorization = `Bearer ${token}`;

    const redirectOn401 = options.redirectOn401 !== false;

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, config);
      
      if (response.status === 401) {
        if (redirectOn401) {
            // Handle unauthorized (redirect to login)
            // CRITICAL: Clear local storage to prevent redirect loop in AuthContext
            localStorage.removeItem('ucm-auth');
            window.location.href = '/login';
        }
        throw new Error('Unauthorized');
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `API Error: ${response.status}`);
      }

      // Return empty object for 204 No Content
      if (response.status === 204) return {};

      return await response.json();
    } catch (error) {
      console.error('API Request Failed:', error);
      throw error;
    }
  }

  get(endpoint) {
    return this.request(endpoint, { method: 'GET' });
  }

  post(endpoint, data) {
    return this.request(endpoint, { 
      method: 'POST', 
      body: JSON.stringify(data) 
    });
  }

  put(endpoint, data) {
    return this.request(endpoint, { 
      method: 'PUT', 
      body: JSON.stringify(data) 
    });
  }

  delete(endpoint) {
    return this.request(endpoint, { method: 'DELETE' });
  }
}

export const api = new ApiClient();
