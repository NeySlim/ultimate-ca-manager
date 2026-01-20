import { api } from '../../../core/api/client';

export const ValidationService = {
  getCRLs: async () => {
    const response = await api.get('/crl');
    return response.data;
  },
  
  regenerateCRL: async (caId) => {
    const response = await api.post(`/crl/${caId}/regenerate`);
    return response.data;
  },
  
  getOCSPStatus: async () => {
    const response = await api.get('/ocsp/status');
    return response.data;
  },
  
  getOCSPStats: async () => {
    const response = await api.get('/ocsp/stats');
    return response.data;
  }
};
