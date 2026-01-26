/**
 * Certificates React Query Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { certificatesApi } from '../services/api/certificatesApi';

export const certificatesKeys = {
  all: ['certificates'],
  lists: () => [...certificatesKeys.all, 'list'],
  list: (params) => [...certificatesKeys.lists(), params],
  details: () => [...certificatesKeys.all, 'detail'],
  detail: (id) => [...certificatesKeys.details(), id],
};

export const useCertificates = (params = {}) => {
  return useQuery({
    queryKey: certificatesKeys.list(params),
    queryFn: () => certificatesApi.getAll(params),
  });
};

export const useCertificate = (id) => {
  return useQuery({
    queryKey: certificatesKeys.detail(id),
    queryFn: () => certificatesApi.getById(id),
    enabled: !!id,
  });
};

export const useRevokeCertificate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }) => certificatesApi.revoke(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: certificatesKeys.all });
    },
  });
};

export const useRenewCertificate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: certificatesApi.renew,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: certificatesKeys.all });
    },
  });
};

export const useIssueCertificate = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: certificatesApi.issue,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: certificatesKeys.all });
    },
  });
};
