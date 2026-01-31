/**
 * Hook for auto-refreshing data based on WebSocket events
 * Use this in list pages to automatically refresh when relevant changes occur
 */

import { useEffect, useCallback, useRef } from 'react';
import { useWebSocket, EventType } from './useWebSocket';

/**
 * Hook that triggers a refresh callback when relevant WebSocket events occur
 * @param {Object} options
 * @param {Function} options.onRefresh - Callback to refresh data
 * @param {string[]} options.eventTypes - Event types to listen for
 * @param {number} options.debounceMs - Debounce multiple events (default: 500ms)
 */
export function useAutoRefresh({ onRefresh, eventTypes = [], debounceMs = 500 }) {
  const { subscribe, isConnected } = useWebSocket({ showToasts: true });
  const timeoutRef = useRef(null);
  const pendingRefreshRef = useRef(false);
  
  const debouncedRefresh = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    
    pendingRefreshRef.current = true;
    
    timeoutRef.current = setTimeout(() => {
      if (pendingRefreshRef.current && onRefresh) {
        onRefresh();
        pendingRefreshRef.current = false;
      }
    }, debounceMs);
  }, [onRefresh, debounceMs]);
  
  useEffect(() => {
    if (!isConnected || eventTypes.length === 0) {
      return;
    }
    
    // Subscribe to all specified event types
    const unsubscribes = eventTypes.map((eventType) => {
      return subscribe(eventType, () => {
        debouncedRefresh();
      });
    });
    
    // Cleanup
    return () => {
      unsubscribes.forEach((unsubscribe) => unsubscribe());
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [isConnected, eventTypes, subscribe, debouncedRefresh]);
  
  return { isConnected };
}

// Predefined event type groups for common use cases
export const CertificateEvents = [
  EventType.CERTIFICATE_ISSUED,
  EventType.CERTIFICATE_REVOKED,
  EventType.CERTIFICATE_RENEWED,
  EventType.CERTIFICATE_DELETED,
];

export const CAEvents = [
  EventType.CA_CREATED,
  EventType.CA_UPDATED,
  EventType.CA_DELETED,
  EventType.CA_REVOKED,
];

export const UserEvents = [
  EventType.USER_CREATED,
  EventType.USER_UPDATED,
  EventType.USER_DELETED,
];

export const GroupEvents = [
  EventType.GROUP_CREATED,
  EventType.GROUP_UPDATED,
  EventType.GROUP_DELETED,
];

export const CRLEvents = [
  EventType.CRL_REGENERATED,
  EventType.CRL_PUBLISHED,
];

export const AllPKIEvents = [
  ...CertificateEvents,
  ...CAEvents,
  ...CRLEvents,
];

export default useAutoRefresh;
