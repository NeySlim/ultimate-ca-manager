/**
 * WebSocket Connection Indicator
 * Shows real-time connection status in the UI
 */

import React from 'react';
import { useWebSocket, ConnectionState } from '../hooks/useWebSocket';
import { WifiHigh, WifiSlash, CircleNotch } from '@phosphor-icons/react';
import { cn } from '../lib/utils';

const stateConfig = {
  [ConnectionState.CONNECTED]: {
    icon: WifiHigh,
    color: 'text-green-500',
    label: 'Real-time updates active',
    pulse: false,
  },
  [ConnectionState.CONNECTING]: {
    icon: CircleNotch,
    color: 'text-yellow-500',
    label: 'Connecting...',
    pulse: true,
  },
  [ConnectionState.DISCONNECTED]: {
    icon: WifiSlash,
    color: 'text-text-tertiary',
    label: 'Real-time updates disabled',
    pulse: false,
  },
  [ConnectionState.ERROR]: {
    icon: WifiSlash,
    color: 'text-red-500',
    label: 'Connection error',
    pulse: false,
  },
};

export function WebSocketIndicator({ className, showLabel = false }) {
  const { connectionState, isConnected, connect } = useWebSocket({ showToasts: false });
  
  const config = stateConfig[connectionState] || stateConfig[ConnectionState.DISCONNECTED];
  const Icon = config.icon;
  
  const handleClick = () => {
    if (!isConnected) {
      connect();
    }
  };
  
  return (
    <button
      onClick={handleClick}
      title={config.label}
      className={cn(
        'flex items-center gap-1.5 p-1 rounded hover:bg-bg-tertiary transition-colors',
        className
      )}
    >
      <Icon
        size={16}
        weight="bold"
        className={cn(
          config.color,
          config.pulse && 'animate-spin'
        )}
      />
      {showLabel && (
        <span className={cn('text-xs', config.color)}>
          {isConnected ? 'Live' : 'Offline'}
        </span>
      )}
    </button>
  );
}

export default WebSocketIndicator;
