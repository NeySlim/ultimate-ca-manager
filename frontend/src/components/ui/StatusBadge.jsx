import React from 'react';
import { Badge } from './Badge';

/**
 * StatusBadge - Intelligent badge with contextual colors
 * Automatically assigns colors based on status/type
 */
export const StatusBadge = ({ 
  status, 
  context = 'generic',
  className = '',
  ...props 
}) => {
  const getVariant = () => {
    const statusLower = (status || '').toLowerCase();
    
    // Certificate statuses
    if (context === 'certificate') {
      if (statusLower === 'valid') return 'active';
      if (statusLower.includes('expir') || statusLower === 'expires soon') return 'warning';
      if (statusLower === 'expired') return 'error';
      if (statusLower === 'revoked') return 'error';
    }
    
    // CA statuses
    if (context === 'ca') {
      if (statusLower === 'root') return 'info';
      if (statusLower === 'intermediate') return 'neutral';
      if (statusLower === 'active') return 'active';
      if (statusLower === 'inactive') return 'error';
    }
    
    // ACME statuses
    if (context === 'acme') {
      if (statusLower === 'valid') return 'active';
      if (statusLower === 'pending') return 'warning';
      if (statusLower === 'failed') return 'error';
      if (statusLower === 'processing') return 'info';
    }
    
    // SCEP statuses
    if (context === 'scep') {
      if (statusLower === 'approved') return 'active';
      if (statusLower === 'pending approval' || statusLower === 'pending') return 'warning';
      if (statusLower === 'rejected') return 'error';
    }
    
    // User statuses
    if (context === 'user') {
      if (statusLower === 'admin') return 'error'; // Red for admin role
      if (statusLower === 'user') return 'neutral';
      if (statusLower === 'active') return 'active';
      if (statusLower === 'locked' || statusLower === 'disabled') return 'error';
    }
    
    // Generic fallback
    if (statusLower.includes('success') || statusLower === 'ok' || statusLower === 'active' || statusLower === 'valid') {
      return 'active';
    }
    if (statusLower.includes('warn') || statusLower === 'pending') {
      return 'warning';
    }
    if (statusLower.includes('error') || statusLower === 'failed' || statusLower === 'revoked' || statusLower === 'expired') {
      return 'error';
    }
    if (statusLower.includes('info')) {
      return 'info';
    }
    
    return 'neutral';
  };

  return (
    <Badge variant={getVariant()} className={className} {...props}>
      {status}
    </Badge>
  );
};
