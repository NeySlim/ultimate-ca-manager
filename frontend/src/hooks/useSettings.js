/**
 * Settings React Query Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { settingsApi } from '../services/api/settingsApi';
import toast from 'react-hot-toast';

export const settingsKeys = {
  all: ['settings'],
  general: () => [...settingsKeys.all, 'general'],
  users: () => [...settingsKeys.all, 'users'],
  dbStats: () => [...settingsKeys.all, 'db-stats'],
};

export const useSettings = () => {
  return useQuery({
    queryKey: settingsKeys.all,
    queryFn: settingsApi.getAll,
  });
};

export const useGeneralSettings = () => {
  return useQuery({
    queryKey: settingsKeys.general(),
    queryFn: settingsApi.getGeneral,
  });
};

export const useUpdateGeneralSettings = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: settingsApi.updateGeneral,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: settingsKeys.general() });
      toast.success('Settings updated successfully');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to update settings');
    },
  });
};

export const useDatabaseStats = () => {
  return useQuery({
    queryKey: settingsKeys.dbStats(),
    queryFn: settingsApi.getDatabaseStats,
  });
};

export const useOptimizeDatabase = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: settingsApi.optimizeDatabase,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: settingsKeys.dbStats() });
      toast.success('Database optimized successfully');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to optimize database');
    },
  });
};

export const useRegenerateHttpsCert = () => {
  return useMutation({
    mutationFn: settingsApi.regenerateHttpsCert,
    onSuccess: () => {
      toast.success('HTTPS certificate regenerated. Service restart required.');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to regenerate certificate');
    },
  });
};

export const useUsers = () => {
  return useQuery({
    queryKey: settingsKeys.users(),
    queryFn: settingsApi.getUsers,
  });
};

export const useCreateUser = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: settingsApi.createUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: settingsKeys.users() });
    },
  });
};
