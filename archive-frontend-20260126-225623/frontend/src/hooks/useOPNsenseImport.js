/**
 * Custom hooks for OPNsense Import
 */
import { useMutation } from '@tanstack/react-query';
import api from '../services/api/api';

/**
 * Hook for testing OPNsense connection
 */
export function useTestOPNsenseConnection() {
  return useMutation({
    mutationFn: async (credentials) => {
      const response = await api.post('/api/v2/import/opnsense/test', credentials);
      return response;
    }
  });
}

/**
 * Hook for importing from OPNsense
 */
export function useImportFromOPNsense() {
  return useMutation({
    mutationFn: async (importData) => {
      const response = await api.post('/api/v2/import/opnsense/import', importData);
      return response;
    }
  });
}
