/**
 * Density Configurations
 * 3 levels: compact, normal, comfortable
 */

import type { DensityLevel, DensityConfig } from '../types/theme';

export const DENSITY_CONFIGS: Record<DensityLevel, DensityConfig> = {
  compact: {
    spacing: {
      xs: 4,
      sm: 6,
      md: 8,
      lg: 12,
      xl: 16,
    },
    fontSize: {
      xs: 10,
      sm: 11,
      md: 12,
      lg: 13,
      xl: 14,
    },
    radius: {
      xs: 1,
      sm: 2,
      md: 2,
      lg: 3,
      xl: 4,
    },
    inputHeight: {
      xs: 24,
      sm: 28,
      md: 32,
      lg: 36,
      xl: 40,
    },
  },
  normal: {
    spacing: {
      xs: 8,
      sm: 10,
      md: 12,
      lg: 16,
      xl: 20,
    },
    fontSize: {
      xs: 12,
      sm: 13,
      md: 14,
      lg: 15,
      xl: 16,
    },
    radius: {
      xs: 2,
      sm: 3,
      md: 4,
      lg: 6,
      xl: 8,
    },
    inputHeight: {
      xs: 30,
      sm: 34,
      md: 38,
      lg: 42,
      xl: 48,
    },
  },
  comfortable: {
    spacing: {
      xs: 12,
      sm: 16,
      md: 20,
      lg: 24,
      xl: 32,
    },
    fontSize: {
      xs: 13,
      sm: 14,
      md: 15,
      lg: 16,
      xl: 18,
    },
    radius: {
      xs: 4,
      sm: 6,
      md: 6,
      lg: 8,
      xl: 12,
    },
    inputHeight: {
      xs: 36,
      sm: 40,
      md: 44,
      lg: 50,
      xl: 56,
    },
  },
};

export const DENSITY_LABELS: Record<DensityLevel, string> = {
  compact: 'Compact',
  normal: 'Normal',
  comfortable: 'Comfortable',
};
