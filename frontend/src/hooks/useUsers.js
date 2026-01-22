/**
 * Users React Query Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { usersApi } from '../services/api/usersApi';
import toast from 'react-hot-toast';

// Query keys
export const usersKeys = {
  all: ['users'],
  lists: () => [...usersKeys.all, 'list'],
  list: (params) => [...usersKeys.lists(), params],
};

/**
 * Get all users
 */
export const useUsers = (params = {}) => {
  return useQuery({
    queryKey: usersKeys.list(params),
    queryFn: () => usersApi.getUsers(params),
  });
};

/**
 * Create user mutation
 */
export const useCreateUser = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: usersApi.createUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
      toast.success('User created successfully');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to create user');
    },
  });
};

/**
 * Update user mutation
 */
export const useUpdateUser = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: usersApi.updateUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
      toast.success('User updated successfully');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to update user');
    },
  });
};

/**
 * Delete user mutation
 */
export const useDeleteUser = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: usersApi.deleteUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
      toast.success('User deleted successfully');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to delete user');
    },
  });
};

/**
 * Import users mutation
 */
export const useImportUsers = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: usersApi.importUsers,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
      const { imported = 0, skipped = 0 } = data;
      toast.success(`Imported ${imported} users, skipped ${skipped}`);
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to import users');
    },
  });
};
