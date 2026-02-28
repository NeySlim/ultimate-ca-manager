/**
 * WebSocket Context for real-time events
 * Single shared Socket.IO connection across the entire app
 */

import { createContext, useContext, useEffect, useRef, useCallback, useState } from 'react';
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

const WebSocketContext = createContext(null);

// Toast handler (module-level, no React dependency)
function handleEventToast(payload) {
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
    case EventType.CERTIFICATE_RENEWED:
      toast.success(`Certificate renewed: ${data.cn}`);
      break;
    case EventType.CERTIFICATE_DELETED:
      toast.info(`Certificate deleted: ${data.cn}`);
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
    case EventType.CA_UPDATED:
      toast.info(`CA updated: ${data.name}`);
      break;
    case EventType.CA_DELETED:
      toast.info(`CA deleted: ${data.name}`);
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
    case EventType.USER_CREATED:
      toast.success(`User created: ${data.username}`);
      break;
    case EventType.USER_DELETED:
      toast.info(`User deactivated: ${data.username}`);
      break;
    case EventType.GROUP_CREATED:
      toast.success(`Group created: ${data.name}`);
      break;
    case EventType.GROUP_DELETED:
      toast.info(`Group deleted: ${data.name}`);
      break;
    case EventType.SYSTEM_ALERT: {
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
    }
    case EventType.AUDIT_CRITICAL:
      toast.error(`Critical action: ${data.action}`, {
        description: `User: ${data.user} | Resource: ${data.resource}`,
        duration: 10000,
      });
      break;
    default:
      break;
  }
}

/**
 * WebSocket Provider — mounts a single Socket.IO connection for the app.
 * Wrap your app (inside AuthProvider) with this.
 */
export function WebSocketProvider({ children }) {
  const { isAuthenticated } = useAuth();
  const socketRef = useRef(null);
  const [connectionState, setConnectionState] = useState(ConnectionState.DISCONNECTED);
  const [lastEvent, setLastEvent] = useState(null);
  const eventHandlersRef = useRef(new Map());
  
  const connect = useCallback(() => {
    if (socketRef.current?.connected) return;
    
    setConnectionState(ConnectionState.CONNECTING);
    
    const socket = io(window.location.origin, {
      path: '/socket.io',
      transports: ['websocket', 'polling'],
      withCredentials: true,
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 20000,
    });
    
    socket.on('connect', () => {
      if (import.meta.env.DEV) console.log('[WebSocket] Connected');
      setConnectionState(ConnectionState.CONNECTED);
    });
    
    socket.on('disconnect', (reason) => {
      if (import.meta.env.DEV) console.log('[WebSocket] Disconnected:', reason);
      setConnectionState(ConnectionState.DISCONNECTED);
    });
    
    socket.on('connect_error', (error) => {
      if (import.meta.env.DEV) console.error('[WebSocket] Connection error:', error);
      setConnectionState(ConnectionState.ERROR);
    });
    
    socket.on('connected', (data) => {
      if (import.meta.env.DEV) console.log('[WebSocket] Server confirmed connection:', data);
    });
    
    socket.on('event', (payload) => {
      if (import.meta.env.DEV) console.log('[WebSocket] Event received:', payload);
      setLastEvent(payload);
      
      // Call type-specific handlers
      const handlers = eventHandlersRef.current.get(payload.type);
      if (handlers) {
        handlers.forEach((handler) => handler(payload.data, payload));
      }
      
      // Show toast notifications
      handleEventToast(payload);
    });
    
    socket.on('pong', () => {});
    
    socketRef.current = socket;
  }, []);
  
  const disconnect = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.disconnect();
      socketRef.current = null;
      setConnectionState(ConnectionState.DISCONNECTED);
    }
  }, []);
  
  const subscribe = useCallback((eventType, handler) => {
    if (!eventHandlersRef.current.has(eventType)) {
      eventHandlersRef.current.set(eventType, new Set());
    }
    eventHandlersRef.current.get(eventType).add(handler);
    return () => {
      const handlers = eventHandlersRef.current.get(eventType);
      if (handlers) handlers.delete(handler);
    };
  }, []);
  
  const subscribeToRoom = useCallback((rooms) => {
    if (socketRef.current?.connected) {
      socketRef.current.emit('subscribe', { rooms: Array.isArray(rooms) ? rooms : [rooms] });
    }
  }, []);
  
  const unsubscribeFromRoom = useCallback((rooms) => {
    if (socketRef.current?.connected) {
      socketRef.current.emit('unsubscribe', { rooms: Array.isArray(rooms) ? rooms : [rooms] });
    }
  }, []);
  
  const ping = useCallback(() => {
    if (socketRef.current?.connected) {
      socketRef.current.emit('ping');
    }
  }, []);
  
  // Auto-connect/disconnect based on auth state
  useEffect(() => {
    if (isAuthenticated) {
      connect();
    } else {
      disconnect();
    }
    return () => disconnect();
  }, [isAuthenticated, connect, disconnect]);
  
  const value = {
    connectionState,
    isConnected: connectionState === ConnectionState.CONNECTED,
    lastEvent,
    connect,
    disconnect,
    subscribe,
    subscribeToRoom,
    unsubscribeFromRoom,
    ping,
  };
  
  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
}

/**
 * Hook to access the shared WebSocket connection.
 * Options are ignored (kept for backward compat) — toasts are always shown globally.
 */
export function useWebSocket(_options = {}) {
  const ctx = useContext(WebSocketContext);
  if (!ctx) {
    // Fallback for components outside provider (e.g., tests)
    return {
      connectionState: ConnectionState.DISCONNECTED,
      isConnected: false,
      lastEvent: null,
      connect: () => {},
      disconnect: () => {},
      subscribe: () => () => {},
      subscribeToRoom: () => {},
      unsubscribeFromRoom: () => {},
      ping: () => {},
    };
  }
  return ctx;
}

export default useWebSocket;
