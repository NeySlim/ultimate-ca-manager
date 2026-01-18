// API Client - Simple & Robust
class API {
  constructor(baseURL = '') {
    this.baseURL = baseURL;
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      credentials: 'same-origin',
      ...options
    };

    if (options.body && typeof options.body === 'object') {
      config.body = JSON.stringify(options.body);
    }

    try {
      const response = await fetch(url, config);
      const data = await response.json();

      if (!response.ok) {
        // Server returned an error
        const error = new Error(data.message || `HTTP ${response.status}`);
        error.status = response.status;
        error.data = data;
        throw error;
      }

      return data;
    } catch (error) {
      // Network error or parsing error
      if (!error.status) {
        error.message = error.message || 'Network error';
      }
      throw error;
    }
  }

  get(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'GET' });
  }

  post(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'POST', body });
  }

  put(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'PUT', body });
  }

  delete(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'DELETE' });
  }
}

// Auth API
class AuthAPI extends API {
  async login(username, password) {
    return this.post('/api/auth/login', { username, password });
  }

  async logout() {
    return this.post('/api/auth/logout');
  }

  async verify() {
    return this.get('/api/auth/verify');
  }

  async getCurrentUser() {
    return this.get('/api/auth/me');
  }
}

// Certificates API
class CertificatesAPI extends API {
  async list(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.get(`/api/certificates${query ? '?' + query : ''}`);
  }

  async get(id) {
    return this.get(`/api/certificates/${id}`);
  }

  async create(data) {
    return this.post('/api/certificates', data);
  }

  async revoke(id, reason) {
    return this.post(`/api/certificates/${id}/revoke`, { reason });
  }

  async delete(id) {
    return this.delete(`/api/certificates/${id}`);
  }

  async download(id, format = 'pem') {
    return this.get(`/api/certificates/${id}/download?format=${format}`);
  }
}

// CAs API
class CAsAPI extends API {
  async list() {
    return this.get('/api/cas');
  }

  async get(id) {
    return this.get(`/api/cas/${id}`);
  }

  async create(data) {
    return this.post('/api/cas', data);
  }

  async update(id, data) {
    return this.put(`/api/cas/${id}`, data);
  }

  async delete(id) {
    return this.delete(`/api/cas/${id}`);
  }
}

// Dashboard API
class DashboardAPI extends API {
  async getStats() {
    return this.get('/api/dashboard/stats');
  }
}

// Export unified API client
const api = {
  auth: new AuthAPI(),
  certificates: new CertificatesAPI(),
  cas: new CAsAPI(),
  dashboard: new DashboardAPI()
};

if (typeof window !== 'undefined') {
  window.api = api;
}
