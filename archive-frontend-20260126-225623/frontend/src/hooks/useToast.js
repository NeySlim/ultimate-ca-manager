import toast from 'react-hot-toast';

/**
 * useToast Hook
 * Wrapper around react-hot-toast with predefined styles
 */

export function useToast() {
  const success = (message, options = {}) => {
    return toast.success(message, {
      duration: 3000,
      icon: '✓',
      style: {
        background: 'var(--bg-secondary)',
        color: 'var(--text-primary)',
        border: '1px solid var(--status-success)',
        borderRadius: 'var(--radius)',
      },
      ...options,
    });
  };

  const error = (message, options = {}) => {
    return toast.error(message, {
      duration: 4000,
      icon: '✗',
      style: {
        background: 'var(--bg-secondary)',
        color: 'var(--text-primary)',
        border: '1px solid var(--status-danger)',
        borderRadius: 'var(--radius)',
      },
      ...options,
    });
  };

  const loading = (message, options = {}) => {
    return toast.loading(message, {
      style: {
        background: 'var(--bg-secondary)',
        color: 'var(--text-primary)',
        border: '1px solid var(--border-primary)',
        borderRadius: 'var(--radius)',
      },
      ...options,
    });
  };

  const info = (message, options = {}) => {
    return toast(message, {
      duration: 3000,
      icon: 'ℹ️',
      style: {
        background: 'var(--bg-secondary)',
        color: 'var(--text-primary)',
        border: '1px solid var(--status-info)',
        borderRadius: 'var(--radius)',
      },
      ...options,
    });
  };

  const promise = (promise, messages, options = {}) => {
    return toast.promise(
      promise,
      {
        loading: messages.loading || 'Loading...',
        success: messages.success || 'Success!',
        error: messages.error || 'Error!',
      },
      {
        style: {
          background: 'var(--bg-secondary)',
          color: 'var(--text-primary)',
          border: '1px solid var(--border-primary)',
          borderRadius: 'var(--radius)',
        },
        ...options,
      }
    );
  };

  return {
    success,
    error,
    loading,
    info,
    promise,
    dismiss: toast.dismiss,
  };
}

export default useToast;
