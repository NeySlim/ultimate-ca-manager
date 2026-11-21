/**
 * The live connection, the product's addition to the status bar, drawn as the mockup draws the bar's
 * state links (.ha-link and its tone): its state in words for assistive technology and as a tooltip,
 * a click reconnecting while it is not connected.
 */
import { useTranslation } from 'react-i18next'
import { useWebSocket, ConnectionState } from '../hooks/useWebSocket'
import { Icon } from './atelier/Icon'

const STATES = {
  [ConnectionState.CONNECTED]: ['good', 'websocket.status.active'],
  [ConnectionState.CONNECTING]: ['warn', 'websocket.status.connecting'],
  [ConnectionState.DISCONNECTED]: [null, 'websocket.status.disabled'],
  [ConnectionState.ERROR]: ['bad', 'websocket.status.error'],
}

export function WebSocketIndicator() {
  const { connectionState, isConnected, connect } = useWebSocket({ showToasts: false })
  const { t } = useTranslation()
  const [tone, key] = STATES[connectionState] || STATES[ConnectionState.DISCONNECTED]
  const label = t(key)
  return (
    <button type="button" className={tone ? `ha-link ${tone}` : 'ha-link'} id="ws-button" aria-label={label} title={label}
      onClick={() => { if (!isConnected) connect() }}>
      <Icon name="plug" />
    </button>
  )
}

export default WebSocketIndicator
