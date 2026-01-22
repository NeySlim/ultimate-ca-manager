/**
 * Dashboard React Query Hooks
 */
import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '../services/api/dashboardApi';

// Query keys
export const dashboardKeys = {
  all: ['dashboard'],
  stats: () => [...dashboardKeys.all, 'stats'],
  overview: () => [...dashboardKeys.all, 'overview'],
  activity: (limit) => [...dashboardKeys.all, 'activity', limit],
  expiringCerts: (limit) => [...dashboardKeys.all, 'expiring-certs', limit],
};

/**
 * Hook to get dashboard stats
 */
export const useDashboardStats = () => {
  return useQuery({
    queryKey: dashboardKeys.stats(),
    queryFn: dashboardApi.getStats,
  });
};

/**
 * Hook to get overview stats (public)
 */
export const useDashboardOverview = () => {
  return useQuery({
    queryKey: dashboardKeys.overview(),
    queryFn: dashboardApi.getOverview,
  });
};

/**
 * Hook to get recent activity
 */
export const useDashboardActivity = (limit = 20) => {
  return useQuery({
    queryKey: dashboardKeys.activity(limit),
    queryFn: () => dashboardApi.getActivity(limit),
  });
};

/**
 * Hook to get expiring certificates
 */
export const useDashboardExpiringCerts = (limit = 10) => {
  return useQuery({
    queryKey: dashboardKeys.expiringCerts(limit),
    queryFn: () => dashboardApi.getExpiringCerts(limit),
  });
};
