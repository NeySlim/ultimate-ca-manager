/**
 * CAs React Query Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { casApi } from '../services/api/casApi';

export const casKeys = {
  all: ['cas'],
  lists: () => [...casKeys.all, 'list'],
  list: (params) => [...casKeys.lists(), params],
  details: () => [...casKeys.all, 'detail'],
  detail: (id) => [...casKeys.details(), id],
};

export const useCAs = (params = {}) => {
  return useQuery({
    queryKey: casKeys.list(params),
    queryFn: () => casApi.getAll(params),
  });
};

export const useCA = (id) => {
  return useQuery({
    queryKey: casKeys.detail(id),
    queryFn: () => casApi.getById(id),
    enabled: !!id,
  });
};

export const useCreateCA = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: casApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: casKeys.lists() });
    },
  });
};

export const useUpdateCA = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => casApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: casKeys.all });
    },
  });
};

export const useDeleteCA = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: casApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: casKeys.lists() });
    },
  });
};
