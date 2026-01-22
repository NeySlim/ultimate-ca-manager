/**
 * Templates React Query Hooks
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { templatesApi } from '../services/api/templatesApi';
import toast from 'react-hot-toast';

// Query keys
export const templatesKeys = {
  all: ['templates'],
  lists: () => [...templatesKeys.all, 'list'],
  list: (params) => [...templatesKeys.lists(), params],
};

/**
 * Get all templates
 */
export const useTemplates = (params = {}) => {
  return useQuery({
    queryKey: templatesKeys.list(params),
    queryFn: () => templatesApi.getTemplates(params),
  });
};

/**
 * Create template mutation
 */
export const useCreateTemplate = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: templatesApi.createTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templatesKeys.all });
      toast.success('Template created successfully');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to create template');
    },
  });
};

/**
 * Update template mutation
 */
export const useUpdateTemplate = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: templatesApi.updateTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templatesKeys.all });
      toast.success('Template updated successfully');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to update template');
    },
  });
};

/**
 * Delete template mutation
 */
export const useDeleteTemplate = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: templatesApi.deleteTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templatesKeys.all });
      toast.success('Template deleted successfully');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Failed to delete template');
    },
  });
};
