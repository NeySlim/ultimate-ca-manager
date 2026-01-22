/**
 * CSRs React Query Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { csrsApi } from '../services/api/csrsApi';

export const csrsKeys = {
  all: ['csrs'],
  lists: () => [...csrsKeys.all, 'list'],
  list: (params) => [...csrsKeys.lists(), params],
  details: () => [...csrsKeys.all, 'detail'],
  detail: (id) => [...csrsKeys.details(), id],
};

export const useCSRs = (params = {}) => {
  return useQuery({
    queryKey: csrsKeys.list(params),
    queryFn: () => csrsApi.getAll(params),
  });
};

export const useCSR = (id) => {
  return useQuery({
    queryKey: csrsKeys.detail(id),
    queryFn: () => csrsApi.getById(id),
    enabled: !!id,
  });
};

export const useApproveCSR = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, caId }) => csrsApi.approve(id, caId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: csrsKeys.all });
    },
  });
};

export const useRejectCSR = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }) => csrsApi.reject(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: csrsKeys.all });
    },
  });
};

export const useDeleteCSR = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: csrsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: csrsKeys.lists() });
    },
  });
};
