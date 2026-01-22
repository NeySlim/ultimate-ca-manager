/**
 * SCEP React Query Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { scepApi } from '../services/api/scepApi';

export const scepKeys = {
  all: ['scep'],
  settings: () => [...scepKeys.all, 'settings'],
  stats: () => [...scepKeys.all, 'stats'],
  requests: (params) => [...scepKeys.all, 'requests', params],
};

export const useSCEPSettings = () => {
  return useQuery({
    queryKey: scepKeys.settings(),
    queryFn: scepApi.getSettings,
  });
};

export const useSCEPStats = () => {
  return useQuery({
    queryKey: scepKeys.stats(),
    queryFn: scepApi.getStats,
  });
};

export const useSCEPRequests = (params = {}) => {
  return useQuery({
    queryKey: scepKeys.requests(params),
    queryFn: () => scepApi.getRequests(params),
  });
};

export const useUpdateSCEPSettings = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: scepApi.updateSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: scepKeys.settings() });
    },
  });
};
