// UCM API Client
// Base client for all API calls with auth handling

const API_BASE = '/api/v2';

class APIError extends Error {
  constructor(message, status, data) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.data = data;
  }
}

class APIClient {
  constructor() {
    this.baseURL = API_BASE;
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      credentials: 'include', // Important for session cookies
      ...options
    };

    try {
      const response = await fetch(url, config);
      
      // Handle 401 Unauthorized
      if (response.status === 401) {
        // Redirect to login
        window.location.href = '/login';
        throw new APIError('Unauthorized', 401, null);
      }

      // Handle other errors
      if (!response.ok) {
        let errorData;
        try {
          errorData = await response.json();
        } catch {
          errorData = { message: response.statusText };
        }
        throw new APIError(
          errorData.message || `HTTP ${response.status}`,
          response.status,
          errorData
        );
      }

      // Handle 204 No Content
      if (response.status === 204) {
        return null;
      }

      // Parse JSON response
      const data = await response.json();
      return data;

    } catch (error) {
      if (error instanceof APIError) {
        throw error;
      }
      // Network errors
      throw new APIError(error.message, 0, null);
    }
  }

  // GET request
  async get(endpoint, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const url = queryString ? `${endpoint}?${queryString}` : endpoint;
    return this.request(url, { method: 'GET' });
  }

  // POST request
  async post(endpoint, data = null) {
    return this.request(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : null
    });
  }

  // PUT request
  async put(endpoint, data = null) {
    return this.request(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : null
    });
  }

  // DELETE request
  async delete(endpoint) {
    return this.request(endpoint, { method: 'DELETE' });
  }

  // PATCH request
  async patch(endpoint, data = null) {
    return this.request(endpoint, {
      method: 'PATCH',
      body: data ? JSON.stringify(data) : null
    });
  }
}

// Auth API
export const authAPI = {
  async login(username, password) {
    const api = new APIClient();
    return api.post('/auth/login', { username, password });
  },

  async logout() {
    const api = new APIClient();
    return api.post('/auth/logout');
  },

  async getCurrentUser() {
    const api = new APIClient();
    return api.get('/auth/me');
  },

  async checkWebAuthn() {
    const api = new APIClient();
    return api.get('/auth/webauthn/available');
  }
};

// Certificates API
export const certificatesAPI = {
  async list(params = {}) {
    const api = new APIClient();
    return api.get('/certificates', params);
  },

  async get(id) {
    const api = new APIClient();
    return api.get(`/certificates/${id}`);
  },

  async create(data) {
    const api = new APIClient();
    return api.post('/certificates', data);
  },

  async revoke(id, reason = 'unspecified') {
    const api = new APIClient();
    return api.post(`/certificates/${id}/revoke`, { reason });
  },

  async download(id, format = 'pem') {
    const api = new APIClient();
    return api.get(`/certificates/${id}/download`, { format });
  }
};

// CAs API
export const casAPI = {
  async list() {
    const api = new APIClient();
    return api.get('/cas');
  },

  async get(id) {
    const api = new APIClient();
    return api.get(`/cas/${id}`);
  },

  async create(data) {
    const api = new APIClient();
    return api.post('/cas', data);
  },

  async tree() {
    const api = new APIClient();
    return api.get('/cas/tree');
  }
};

// Stats API
export const statsAPI = {
  async dashboard() {
    const api = new APIClient();
    return api.get('/stats/dashboard');
  }
};

export default APIClient;
