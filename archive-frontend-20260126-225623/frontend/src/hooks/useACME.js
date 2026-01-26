/**
 * ACME React Query Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { acmeApi } from '../services/api/acmeApi';

export const acmeKeys = {
  all: ['acme'],
  settings: () => [...acmeKeys.all, 'settings'],
  stats: () => [...acmeKeys.all, 'stats'],
  accounts: (params) => [...acmeKeys.all, 'accounts', params],
  orders: (params) => [...acmeKeys.all, 'orders', params],
};

export const useACMESettings = () => {
  return useQuery({
    queryKey: acmeKeys.settings(),
    queryFn: acmeApi.getSettings,
  });
};

export const useACMEStats = () => {
  return useQuery({
    queryKey: acmeKeys.stats(),
    queryFn: acmeApi.getStats,
  });
};

export const useACMEAccounts = (params = {}) => {
  return useQuery({
    queryKey: acmeKeys.accounts(params),
    queryFn: () => acmeApi.getAccounts(params),
  });
};

export const useACMEOrders = (params = {}) => {
  return useQuery({
    queryKey: acmeKeys.orders(params),
    queryFn: () => acmeApi.getOrders(params),
  });
};

export const useUpdateACMESettings = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: acmeApi.updateSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: acmeKeys.settings() });
    },
  });
};
