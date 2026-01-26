/**
 * Account/Profile React Query Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { accountApi } from '../services/api/accountApi';

export const accountKeys = {
  all: ['account'],
  profile: () => [...accountKeys.all, 'profile'],
  activity: (params) => [...accountKeys.all, 'activity', params],
  sessions: () => [...accountKeys.all, 'sessions'],
};

export const useProfile = () => {
  return useQuery({
    queryKey: accountKeys.profile(),
    queryFn: accountApi.getProfile,
  });
};

export const useUpdateProfile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: accountApi.updateProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: accountKeys.profile() });
    },
  });
};

export const useChangePassword = () => {
  return useMutation({
    mutationFn: ({ currentPassword, newPassword }) =>
      accountApi.changePassword(currentPassword, newPassword),
  });
};

export const useAccountActivity = (params = {}) => {
  return useQuery({
    queryKey: accountKeys.activity(params),
    queryFn: () => accountApi.getActivity(params),
  });
};

export const useSessions = () => {
  return useQuery({
    queryKey: accountKeys.sessions(),
    queryFn: accountApi.getSessions,
  });
};

export const useRevokeSession = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: accountApi.revokeSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: accountKeys.sessions() });
    },
  });
};

export const useRevokeAllSessions = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: accountApi.revokeAllSessions,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: accountKeys.sessions() });
    },
  });
};
