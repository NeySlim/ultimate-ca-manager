const API_BASE = '/api/v2';

class ApiClient {
  async request(endpoint, options = {}) {
    // If endpoint already starts with /api, use it as is
    // Otherwise prepend API_BASE
    const url = endpoint.startsWith('/api') ? endpoint : `${API_BASE}${endpoint}`;

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
      const response = await fetch(url, config);
      
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
        let errorData = {};
        try {
            const text = await response.text();
            if (text && text.length > 0) {
                errorData = JSON.parse(text);
            }
        } catch (e) {
            // Ignore parse error for error responses
        }
        throw new Error(errorData.message || `API Error: ${response.status}`);
      }

      // Return empty object for 204 No Content
      if (response.status === 204) return {};

      // Safe JSON parsing
      const text = await response.text();
      try {
          return text ? JSON.parse(text) : {};
      } catch (e) {
          console.error('JSON Parse Error:', e, text.substring(0, 100));
          throw new Error('Invalid JSON response from server');
      }
    } catch (error) {
      console.error('API Request Failed:', error);
      throw error;
    }
  }

  get(endpoint, options = {}) {
    return this.request(endpoint, { method: 'GET', ...options });
  }

  post(endpoint, data, options = {}) {
    return this.request(endpoint, { 
      method: 'POST', 
      body: JSON.stringify(data),
      ...options
    });
  }

  put(endpoint, data, options = {}) {
    return this.request(endpoint, { 
      method: 'PUT', 
      body: JSON.stringify(data),
      ...options
    });
  }

  delete(endpoint, options = {}) {
    return this.request(endpoint, { method: 'DELETE', ...options });
  }
}

export const api = new ApiClient();
