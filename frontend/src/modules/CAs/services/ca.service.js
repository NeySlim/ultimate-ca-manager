import { api } from '../../../core/api/client';

class CAService {
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
