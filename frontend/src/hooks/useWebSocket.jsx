/**
 * WebSocket Context for real-time events
 * Single shared Socket.IO connection across the entire app
 */

import { createContext, useContext, useEffect, useRef, useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { io } from 'socket.io-client';
import { useAuth } from '../contexts/AuthContext';
import { useNotification } from '../contexts/NotificationContext';
import { API_ANSWERED_EVENT } from '../services/apiClient';

// Event type constants (matches backend EventType enum)
export const EventType = {
  // Certificate events
  CERTIFICATE_ISSUED: 'certificate.issued',
  CERTIFICATE_REVOKED: 'certificate.revoked',
  CERTIFICATE_UNHELD: 'certificate.unheld',
  CERTIFICATE_EXPIRING: 'certificate.expiring',
  CERTIFICATE_RENEWED: 'certificate.renewed',
  CERTIFICATE_DELETED: 'certificate.deleted',
  CERTIFICATE_BINDING_LEFT_BEHIND: 'certificate.binding_left_behind',
  
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

  // Discovery events
  DISCOVERY_SCAN_STARTED: 'discovery.scan_started',
  DISCOVERY_SCAN_PROGRESS: 'discovery.scan_progress',
  DISCOVERY_SCAN_COMPLETE: 'discovery.scan_complete',
  DISCOVERY_NEW_CERT: 'discovery.new_certificate',
  DISCOVERY_CERT_CHANGED: 'discovery.cert_changed',
};

// Connection states
export const ConnectionState = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  ERROR: 'error',
};

const WebSocketContext = createContext(null);

// A socket the server closed (a session renewal) or a handshake it refused (session check
// unavailable, cookie not there yet) is tried again after each delay, then left to a rearm
export const SERVER_CUT_RETRY_MS = [1500, 5000, 15000];
export const SERVER_CUT_RECONNECT_MS = SERVER_CUT_RETRY_MS[0];
// A handshake the server never answers (neither connect nor connect_error) once the transport
// is open is given up after this delay, then tried again on the schedule above
export const HANDSHAKE_WATCHDOG_MS = 20000;
// A rearm (an API answer, the tab shown again) tries once, at most once per this interval
export const REARM_MIN_INTERVAL_MS = 15000;

// A server event means somebody else changed the data. The pages refresh on
// the in-app `ucm:data-changed` bus, which only the acting tab used to fire,
// so another operator's revocation showed a toast beside a stale table.
//
// `user.login` and `user.logout` are deliberately absent: they carry no table
// change worth a reload, and they reach every holder of read:audit.
const DATA_CHANGED_TYPE = {
  'certificate.issued': 'certificate',
  'certificate.revoked': 'certificate',
  'certificate.unheld': 'certificate',
  'certificate.renewed': 'certificate',
  'certificate.deleted': 'certificate',
  'certificate.expiring': 'certificate',
  'certificate.binding_left_behind': 'certificate',
  'ca.created': 'ca',
  'ca.updated': 'ca',
  'ca.deleted': 'ca',
  'ca.revoked': 'ca',
  'crl.regenerated': 'ca',
  'crl.published': 'ca',
  'user.created': 'user',
  'user.updated': 'user',
  'user.deleted': 'user',
  'group.created': 'group',
  'group.updated': 'group',
  'group.deleted': 'group',
};

// A bulk revoke emits one event per certificate. Announcing each one had every
// open tab reload its whole page that many times over, so the announcements
// are collected and sent once the burst is over.
const ANNOUNCE_DELAY_MS = 250;
let pendingResources = null;
let pendingTimer = null;

function flushDataChanges() {
  const resources = pendingResources;
  pendingResources = null;
  pendingTimer = null;
  if (!resources) return;
  for (const resource of resources) {
    window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: resource } }));
  }
}

function queueDataChange(resource) {
  if (!pendingResources) pendingResources = new Set();
  pendingResources.add(resource);
  if (pendingTimer) clearTimeout(pendingTimer);
  pendingTimer = setTimeout(flushDataChanges, ANNOUNCE_DELAY_MS);
}

function announceDataChange(eventType) {
  const resource = DATA_CHANGED_TYPE[String(eventType)];
  if (resource) queueDataChange(resource);
}

// Events that arrived while the socket was down are gone. After a reconnect
// the tables are refreshed wholesale rather than left on what they held.
function announceEverythingChanged() {
  for (const resource of new Set(Object.values(DATA_CHANGED_TYPE))) queueDataChange(resource);
}

/**
 * Maps a WS event to a notification method + message.
 *
 * `t` is the i18next translator, passed in by the provider so this stays a
 * plain function. Events that already have a `notifications.*` key (present in
 * all ten locales) go through it; the rest keep their English sentence rather
 * than inventing keys that would have to be translated ten times.
 */
export function getEventNotification(payload, t) {
  const { type, data } = payload;

  switch (type) {
    case EventType.CERTIFICATE_ISSUED:
      return { method: 'showSuccess', msg: t('notifications.certificateIssued', { name: data.cn }) };
    case EventType.CERTIFICATE_REVOKED:
      return { method: 'showWarning', msg: t('notifications.certificateRevoked', { name: data.cn }) };
    case EventType.CERTIFICATE_EXPIRING: {
      // notifications.certificateExpiring interpolates {{name}} only — it has no
      // slot for the day count. Rather than drop that (it is the whole point of
      // the toast) or add a 10th string, append the existing common.daysLeft.
      const expiring = t('notifications.certificateExpiring', { name: data.cn });
      return {
        method: 'showWarning',
        msg: data.days_left == null
          ? expiring
          : `${expiring} (${t('common.daysLeft', { count: data.days_left })})`,
      };
    }
    case EventType.CERTIFICATE_RENEWED:
      // No notifications.* key exists for this event — left in English on purpose.
      return { method: 'showSuccess', msg: `Certificate renewed: ${data.cn}` };
    case EventType.CERTIFICATE_DELETED:
      return { method: 'showInfo', msg: `Certificate deleted: ${data.cn}` };
    case EventType.CERTIFICATE_BINDING_LEFT_BEHIND:
      return { method: 'showWarning', msg: t('notifications.bindingLeftBehind', {
        name: data.binding?.type === 'https' ? 'HTTPS' : (data.binding?.target_name || '') }) };
    case EventType.CA_CREATED:
      return { method: 'showSuccess', msg: t('notifications.caCreated', { name: data.name }) };
    case EventType.CA_REVOKED:
      return { method: 'showError', msg: t('notifications.caRevoked', { name: data.name }) };
    case EventType.CA_UPDATED:
      return { method: 'showInfo', msg: `CA updated: ${data.name}` };
    case EventType.CA_DELETED:
      return { method: 'showInfo', msg: `CA deleted: ${data.name}` };
    case EventType.CRL_REGENERATED:
      return { method: 'showInfo', msg: t('notifications.crlRegenerated', { name: data.ca_name }) };
    case EventType.USER_LOGIN:
      return { method: 'showInfo', msg: t('notifications.userLoggedIn', { name: data.username }) };
    case EventType.USER_LOGOUT:
      return { method: 'showInfo', msg: t('notifications.userLoggedOut', { name: data.username }) };
    case EventType.USER_CREATED:
      return { method: 'showSuccess', msg: `User created: ${data.username}` };
    case EventType.USER_DELETED:
      return { method: 'showInfo', msg: `User deactivated: ${data.username}` };
    case EventType.GROUP_CREATED:
      return { method: 'showSuccess', msg: `Group created: ${data.name}` };
    case EventType.GROUP_DELETED:
      return { method: 'showInfo', msg: `Group deleted: ${data.name}` };
    case EventType.SYSTEM_ALERT:
      return { method: data.severity === 'critical' || data.severity === 'error' ? 'showError' : data.severity === 'warning' ? 'showWarning' : 'showInfo', msg: data.message };
    case EventType.AUDIT_CRITICAL:
      return { method: 'showError', msg: `Critical: ${data.action} by ${data.user}` };
    default:
      return null;
  }
}

/**
 * WebSocket Provider — mounts a single Socket.IO connection for the app.
 * Wrap your app (inside AuthProvider) with this.
 */
export function WebSocketProvider({ children }) {
  const { isAuthenticated, forcePasswordChange, mustEnroll2fa } = useAuth();
  // The server refuses the socket while a forced change or enrolment is pending
  const ready = isAuthenticated && !forcePasswordChange && !mustEnroll2fa;
  const { t } = useTranslation();
  const { showSuccess, showError, showWarning, showInfo } = useNotification();
  const socketRef = useRef(null);
  const [connectionState, setConnectionState] = useState(ConnectionState.DISCONNECTED);
  const [lastEvent, setLastEvent] = useState(null);
  const eventHandlersRef = useRef(new Map());
  const notifyRef = useRef({ showSuccess, showError, showWarning, showInfo });
  notifyRef.current = { showSuccess, showError, showWarning, showInfo };
  // Same ref trick as notifyRef: `connect` is memoized with an empty dep list,
  // so the handler must read the *current* translator (language can change).
  const tRef = useRef(t);
  tRef.current = t;
  const muteUntilRef = useRef(0);
  const hasConnectedRef = useRef(false);
  const reconnectTimerRef = useRef(null);
  const retryStepRef = useRef(0);
  const lastRearmRef = useRef(-Infinity);
  const handshakeTimerRef = useRef(null);
  
  const connect = useCallback(() => {
    if (socketRef.current?.connected) return;
    
    setConnectionState(ConnectionState.CONNECTING);
    
    const socket = io(window.location.origin, {
      path: '/socket.io',
      transports: ['websocket'],  // engine.io-client only falls back with tryAllTransports
      withCredentials: true,
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 20000,
    });

    // The next delay of the schedule, none once it is spent: a rearm alone tries again then
    const retryLater = () => {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
      if (retryStepRef.current >= SERVER_CUT_RETRY_MS.length) return;
      const delay = SERVER_CUT_RETRY_MS[retryStepRef.current];
      retryStepRef.current += 1;
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        if (socketRef.current === socket && !socket.connected) socket.connect();
      }, delay);
    };

    const stopWatchdog = () => {
      clearTimeout(handshakeTimerRef.current);
      handshakeTimerRef.current = null;
    };
    socket.io.on('open', () => {
      stopWatchdog();
      handshakeTimerRef.current = setTimeout(() => {
        handshakeTimerRef.current = null;
        if (socketRef.current !== socket || socket.connected) return;
        socket.disconnect();
        setConnectionState(ConnectionState.ERROR);
        retryLater();
      }, HANDSHAKE_WATCHDOG_MS);
    });
    // A transport lost before the answer: the library reconnects, and its next open re-arms
    socket.io.on('close', stopWatchdog);
    
    socket.on('connect', () => {
      if (import.meta.env.DEV) console.log('[WebSocket] Connected');
      stopWatchdog();
      setConnectionState(ConnectionState.CONNECTED);
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
      retryStepRef.current = 0;
      if (hasConnectedRef.current) announceEverythingChanged();
      hasConnectedRef.current = true;
    });
    
    socket.on('disconnect', (reason) => {
      if (import.meta.env.DEV) console.log('[WebSocket] Disconnected:', reason);
      setConnectionState(ConnectionState.DISCONNECTED);
      if (reason !== 'io server disconnect') return;
      retryStepRef.current = 0;
      retryLater();
    });
    
    socket.on('connect_error', (error) => {
      if (import.meta.env.DEV) console.error('[WebSocket] Connection error:', error);
      stopWatchdog();
      setConnectionState(ConnectionState.ERROR);
      // Still active: a transport failure the library retries itself; else the server refused
      if (!socket.active) retryLater();
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
      
      // The tab that acted reloads on its own, and `muteUntilRef` is exactly
      // the window where it knows already.
      if (Date.now() < muteUntilRef.current) return;
      announceDataChange(payload.type);

      const notif = getEventNotification(payload, tRef.current);
      if (notif) {
        notifyRef.current[notif.method]?.(notif.msg);
      }
    });
    
    socket.on('pong', () => {});
    
    socketRef.current = socket;
  }, []);
  
  const disconnect = useCallback(() => {
    clearTimeout(reconnectTimerRef.current);
    reconnectTimerRef.current = null;
    clearTimeout(handshakeTimerRef.current);
    handshakeTimerRef.current = null;
    retryStepRef.current = 0;
    if (socketRef.current) {
      socketRef.current.disconnect();
      socketRef.current = null;
      hasConnectedRef.current = false;
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
  
  // Mute WS toasts briefly (call before local action to prevent double notif)
  const muteToasts = useCallback((ms = 3000) => {
    muteUntilRef.current = Date.now() + ms;
  }, []);
  
  // Auto-connect/disconnect based on auth state
  useEffect(() => {
    if (ready) {
      connect();
    } else {
      disconnect();
    }
    return () => disconnect();
  }, [ready, connect, disconnect]);

  // A socket left closed by the server tries once more at an API answer or when the tab shows
  useEffect(() => {
    if (!ready) return undefined;
    const rearm = () => {
      const socket = socketRef.current;
      if (!socket || socket.connected || socket.active || reconnectTimerRef.current) return;
      const now = Date.now();
      if (now - lastRearmRef.current < REARM_MIN_INTERVAL_MS) return;
      lastRearmRef.current = now;
      socket.connect();
    };
    const onVisibility = () => {
      if (document.visibilityState === 'visible') rearm();
    };
    window.addEventListener(API_ANSWERED_EVENT, rearm);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.removeEventListener(API_ANSWERED_EVENT, rearm);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [ready]);
  
  const value = {
    connectionState,
    isConnected: connectionState === ConnectionState.CONNECTED,
    lastEvent,
    connect,
    disconnect,
    subscribe,
    subscribeToRoom,
    unsubscribeFromRoom,
    muteToasts,
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
      muteToasts: () => {},
      ping: () => {},
    };
  }
  return ctx;
}

export default useWebSocket;
