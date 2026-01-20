import { api } from '../../../core/api/client';

class CAService {
  async getAll() {
    try {
        const response = await api.get('/cas');
        if (response.data) return response.data;
        return response;
    } catch (error) {
        console.error("API Error getAll:", error);
        return [];
    }
  }

  async getHierarchy() {
    try {
        const response = await api.get('/cas/tree');
        // Handle response wrapper { data: [...], status: 'success' }
        if (response.data) return response.data;
        return response; // If middleware already unwrapped it
    } catch (error) {
        console.error("API Error getHierarchy:", error);
        return [];
    }
  }

  async getOrphans() {
    try {
        const response = await api.get('/cas?type=orphan');
        // Handle response wrapper { data: [...], meta: ... }
        if (response.data) return response.data;
        return response; 
    } catch (error) {
        console.error("API Error getOrphans:", error);
        return [];
    }
  }

  async getById(id) {
    try {
        const response = await api.get(`/cas/${id}`);
        if (response.data) return response.data;
        return response;
    } catch (error) {
        console.error("API Error getById:", error);
        throw error;
    }
  }

  async getCertificates(id, params = {}) {
    try {
        const query = new URLSearchParams(params).toString();
        const response = await api.get(`/cas/${id}/certificates?${query}`);
        return response; // Returns { data: [], meta: {} }
    } catch (error) {
        console.error("API Error getCertificates:", error);
        throw error;
    }
  }

  async exportCA(id, format = 'pem', options = {}) {
    try {
        const query = new URLSearchParams({ format, ...options }).toString();
        const response = await api.get(`/cas/${id}/export?${query}`);
        if (response.data) return response.data;
        return response;
    } catch (error) {
        console.error("API Error exportCA:", error);
        throw error;
    }
  }
  
  async createCA(data) {
    try {
        const response = await api.post('/cas', data);
        return response.data || response;
    } catch (error) {
        console.error("API Error createCA:", error);
        throw error;
    }
  }
}

export const caService = new CAService();
