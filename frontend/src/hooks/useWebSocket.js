/**
 * WebSocket hook for real-time events
 * Connects to UCM backend via Socket.IO
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { io } from 'socket.io-client';
import { useAuth } from '../contexts/AuthContext';
import { toast } from 'sonner';

// Event type constants (matches backend EventType enum)
export const EventType = {
  // Certificate events
  CERTIFICATE_ISSUED: 'certificate.issued',
  CERTIFICATE_REVOKED: 'certificate.revoked',
  CERTIFICATE_EXPIRING: 'certificate.expiring',
  CERTIFICATE_RENEWED: 'certificate.renewed',
  CERTIFICATE_DELETED: 'certificate.deleted',
  
  // CA events
  CA_CREATED: 'ca.created',
  CA_UPDATED: 'ca.updated',
  CA_DELETED: 'ca.deleted',
  CA_REVOKED: 'ca.revoked',
  
  // CRL events
  CRL_REGENERATED: 'crl.regenerated',
  CRL_PUBLISHED: 'crl.published',
  
  // User events
  USER_LOGIN: 'user.login',
  USER_LOGOUT: 'user.logout',
  USER_CREATED: 'user.created',
  USER_UPDATED: 'user.updated',
  USER_DELETED: 'user.deleted',
  
  // Group events
  GROUP_CREATED: 'group.created',
  GROUP_UPDATED: 'group.updated',
  GROUP_DELETED: 'group.deleted',
  
  // System events
  SYSTEM_ALERT: 'system.alert',
  SYSTEM_BACKUP: 'system.backup',
  SYSTEM_RESTORE: 'system.restore',
  
  // Audit events
  AUDIT_CRITICAL: 'audit.critical',
};

// Connection states
export const ConnectionState = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  ERROR: 'error',
};

/**
 * Custom hook for WebSocket connection and event handling
 * @param {Object} options - Configuration options
 * @param {boolean} options.autoConnect - Auto-connect when authenticated (default: true)
 * @param {boolean} options.showToasts - Show toast notifications for events (default: true)
 * @param {Function} options.onEvent - Callback for all events
 */
export function useWebSocket(options = {}) {
  const {
    autoConnect = true,
    showToasts = true,
    onEvent,
  } = options;
  
  const { isAuthenticated, csrfToken } = useAuth();
  const socketRef = useRef(null);
  const [connectionState, setConnectionState] = useState(ConnectionState.DISCONNECTED);
  const [lastEvent, setLastEvent] = useState(null);
  const eventHandlersRef = useRef(new Map());
  
  // Connect to WebSocket server
  const connect = useCallback(() => {
    if (socketRef.current?.connected) {
      return;
    }
    
    setConnectionState(ConnectionState.CONNECTING);
    
    const socket = io(window.location.origin, {
      path: '/socket.io',
      transports: ['websocket', 'polling'],
      query: {
        token: csrfToken, // Use CSRF token for auth
      },
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 20000,
    });
    
    socket.on('connect', () => {
      console.log('[WebSocket] Connected');
      setConnectionState(ConnectionState.CONNECTED);
      if (showToasts) {
        toast.success('Real-time updates enabled', { duration: 2000 });
      }
    });
    
    socket.on('disconnect', (reason) => {
      console.log('[WebSocket] Disconnected:', reason);
      setConnectionState(ConnectionState.DISCONNECTED);
    });
    
    socket.on('connect_error', (error) => {
      console.error('[WebSocket] Connection error:', error);
      setConnectionState(ConnectionState.ERROR);
    });
    
    socket.on('connected', (data) => {
      console.log('[WebSocket] Server confirmed connection:', data);
    });
    
    // Main event handler
    socket.on('event', (payload) => {
      console.log('[WebSocket] Event received:', payload);
      setLastEvent(payload);
      
      // Call global event handler
      if (onEvent) {
        onEvent(payload);
      }
      
      // Call type-specific handlers
      const handlers = eventHandlersRef.current.get(payload.type);
      if (handlers) {
        handlers.forEach((handler) => handler(payload.data, payload));
      }
      
      // Show toast notification based on event type
      if (showToasts) {
        handleEventToast(payload);
      }
    });
    
    socket.on('pong', () => {
      // Keep-alive response
    });
    
    socketRef.current = socket;
  }, [csrfToken, onEvent, showToasts]);
  
  // Disconnect from WebSocket server
  const disconnect = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.disconnect();
      socketRef.current = null;
      setConnectionState(ConnectionState.DISCONNECTED);
    }
  }, []);
  
  // Subscribe to specific event type
  const subscribe = useCallback((eventType, handler) => {
    if (!eventHandlersRef.current.has(eventType)) {
      eventHandlersRef.current.set(eventType, new Set());
    }
    eventHandlersRef.current.get(eventType).add(handler);
    
    // Return unsubscribe function
    return () => {
      const handlers = eventHandlersRef.current.get(eventType);
      if (handlers) {
        handlers.delete(handler);
      }
    };
  }, []);
  
  // Subscribe to a room (e.g., specific CA or certificate)
  const subscribeToRoom = useCallback((rooms) => {
    if (socketRef.current?.connected) {
      socketRef.current.emit('subscribe', { rooms: Array.isArray(rooms) ? rooms : [rooms] });
    }
  }, []);
  
  // Unsubscribe from a room
  const unsubscribeFromRoom = useCallback((rooms) => {
    if (socketRef.current?.connected) {
      socketRef.current.emit('unsubscribe', { rooms: Array.isArray(rooms) ? rooms : [rooms] });
    }
  }, []);
  
  // Send ping to keep connection alive
  const ping = useCallback(() => {
    if (socketRef.current?.connected) {
      socketRef.current.emit('ping');
    }
  }, []);
  
  // Handle toast notifications based on event type
  const handleEventToast = useCallback((payload) => {
    const { type, data } = payload;
    
    switch (type) {
      case EventType.CERTIFICATE_ISSUED:
        toast.success(`Certificate issued: ${data.cn}`, {
          description: `Issued by ${data.issuer}`,
        });
        break;
        
      case EventType.CERTIFICATE_REVOKED:
        toast.warning(`Certificate revoked: ${data.cn}`, {
          description: `Reason: ${data.reason}`,
        });
        break;
        
      case EventType.CERTIFICATE_EXPIRING:
        toast.warning(`Certificate expiring: ${data.cn}`, {
          description: `Expires in ${data.days_left} days`,
        });
        break;
        
      case EventType.CA_CREATED:
        toast.success(`CA created: ${data.name}`, {
          description: `Common Name: ${data.common_name}`,
        });
        break;
        
      case EventType.CA_REVOKED:
        toast.error(`CA revoked: ${data.name}`, {
          description: `Reason: ${data.reason}`,
        });
        break;
        
      case EventType.CRL_REGENERATED:
        toast.info(`CRL regenerated for ${data.ca_name}`, {
          description: `${data.entries_count} entries`,
        });
        break;
        
      case EventType.USER_LOGIN:
        toast.info(`User logged in: ${data.username}`);
        break;
        
      case EventType.USER_LOGOUT:
        toast.info(`User logged out: ${data.username}`);
        break;
        
      case EventType.SYSTEM_ALERT:
        const toastMethod = {
          info: toast.info,
          warning: toast.warning,
          error: toast.error,
          critical: toast.error,
        }[data.severity] || toast.info;
        
        toastMethod(data.message, {
          description: data.alert_type,
          duration: data.severity === 'critical' ? 10000 : 5000,
        });
        break;
        
      case EventType.AUDIT_CRITICAL:
        toast.error(`Critical action: ${data.action}`, {
          description: `User: ${data.user} | Resource: ${data.resource}`,
          duration: 10000,
        });
        break;
        
      default:
        // Don't show toast for unhandled events
        break;
    }
  }, []);
  
  // Auto-connect when authenticated
  useEffect(() => {
    if (autoConnect && isAuthenticated && csrfToken) {
      connect();
    } else if (!isAuthenticated) {
      disconnect();
    }
    
    return () => {
      disconnect();
    };
  }, [autoConnect, isAuthenticated, csrfToken, connect, disconnect]);
  
  return {
    // State
    connectionState,
    isConnected: connectionState === ConnectionState.CONNECTED,
    lastEvent,
    
    // Methods
    connect,
    disconnect,
    subscribe,
    subscribeToRoom,
    unsubscribeFromRoom,
    ping,
  };
}

export default useWebSocket;
