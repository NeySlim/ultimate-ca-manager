import React from 'react';
import { toast, Toaster } from 'react-hot-toast';

/**
 * Notification wrapper for react-hot-toast
 * Replaces @mantine/notifications with consistent API
 */

const defaultOptions = {
  duration: 4000,
  style: {
    background: 'var(--bg-secondary)',
    border: '1px solid var(--border-primary)',
    borderRadius: 'var(--radius)',
    color: 'var(--text-primary)',
    fontSize: '13px',
    padding: '12px 16px',
  },
};

export const notifications = {
  show: ({ title, message, color }) => {
    const text = title && message ? `${title}: ${message}` : (title || message);
    
    switch (color) {
      case 'green':
      case 'success':
        return toast.success(text, defaultOptions);
      case 'red':
      case 'error':
        return toast.error(text, defaultOptions);
      case 'yellow':
      case 'warning':
        return toast(text, { ...defaultOptions, icon: '⚠' });
      case 'blue':
      case 'info':
      default:
        return toast(text, { ...defaultOptions, icon: 'ℹ' });
    }
  },
};

// Re-export Toaster for use in App.jsx
export { Toaster };
