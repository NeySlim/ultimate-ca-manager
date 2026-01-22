/**
 * Settings React Query Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { settingsApi } from '../services/api/settingsApi';

export const settingsKeys = {
  all: ['settings'],
  general: () => [...settingsKeys.all, 'general'],
  users: () => [...settingsKeys.all, 'users'],
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
