/**
 * TrustStore React Query Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { truststoreApi } from '../services/api/truststoreApi';
import toast from 'react-hot-toast';

// Query keys
export const truststoreKeys = {
  all: ['truststore'],
  lists: () => [...truststoreKeys.all, 'list'],
  list: (params) => [...truststoreKeys.lists(), params],
};

/**
 * Get all trusted certificates
 */
export const useTrustStore = (params = {}) => {
  return useQuery({
    queryKey: truststoreKeys.list(params),
    queryFn: () => truststoreApi.getTrustedCerts(params),
  });
};

/**
 * Add trusted certificate mutation
 */
export const useAddTrustedCert = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: truststoreApi.addTrustedCert,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: truststoreKeys.all });
      toast.success('Certificate added to trust store');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to add certificate');
    },
  });
};

/**
 * Remove trusted certificate mutation
 */
export const useRemoveTrustedCert = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: truststoreApi.removeTrustedCert,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: truststoreKeys.all });
      toast.success('Certificate removed from trust store');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to remove certificate');
    },
  });
};

/**
 * Sync trust store mutation
 */
export const useSyncTrustStore = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: truststoreApi.syncTrustStore,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: truststoreKeys.all });
      const synced = data?.data?.synced_count || 0;
      toast.success(`Trust store synchronized successfully (${synced} certificates)`);
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to sync trust store');
    },
  });
};

/**
 * Get single trusted certificate details
 */
export const useTrustedCertDetails = (certId) => {
  return useQuery({
    queryKey: [...truststoreKeys.all, 'detail', certId],
    queryFn: () => truststoreApi.getTrustedCertDetails(certId),
    enabled: !!certId,
  });
};
