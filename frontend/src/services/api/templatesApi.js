/**
 * Templates API Service
 */
import api from './api';

export const templatesApi = {
  /**
   * Get all certificate templates
   * Backend: GET /api/v2/templates
   */
  getTemplates: async (params = {}) => {
    const response = await api.get('/api/v2/templates', { params });
    return response.data; // { data: [...], meta: {} }
  },

  /**
   * Get single template details
   * Backend: GET /api/v2/templates/:id
   */
  getTemplateDetails: async (id) => {
    const response = await api.get(`/api/v2/templates/${id}`);
    return response.data;
  },

  /**
   * Create template
   * Backend: POST /api/v2/templates
   */
  createTemplate: async (templateData) => {
    const response = await api.post('/api/v2/templates', templateData);
    return response.data;
  },

  /**
   * Update template
   * Backend: PUT /api/v2/templates/:id
   */
  updateTemplate: async ({ id, ...templateData }) => {
    const response = await api.put(`/api/v2/templates/${id}`, templateData);
    return response.data;
  },

  /**
   * Delete template
   * Backend: DELETE /api/v2/templates/:id
   */
  deleteTemplate: async (id) => {
    const response = await api.delete(`/api/v2/templates/${id}`);
    return response.data;
  },
};
