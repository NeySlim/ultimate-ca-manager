/** The live connection in the status bar, drawn as the mockup draws the bar's state links (.ha-link and its tone). */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const ws = vi.hoisted(() => ({ state: 'connected', connect: vi.fn() }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))
vi.mock('../../hooks/useWebSocket', () => ({
  ConnectionState: { CONNECTING: 'connecting', CONNECTED: 'connected', DISCONNECTED: 'disconnected', ERROR: 'error' },
  useWebSocket: () => ({ connectionState: ws.state, isConnected: ws.state === 'connected', connect: ws.connect }),
}))

import { WebSocketIndicator } from '../WebSocketIndicator'

describe('WebSocketIndicator', () => {
  beforeEach(() => { ws.connect.mockReset() })

  it.each([
    ['connected', 'good', 'websocket.status.active'],
    ['connecting', 'warn', 'websocket.status.connecting'],
    ['disconnected', null, 'websocket.status.disabled'],
    ['error', 'bad', 'websocket.status.error'],
  ])('%s: the bar\'s state link with its tone and its words', (state, tone, label) => {
    ws.state = state
    render(<WebSocketIndicator />)
    const button = screen.getByRole('button', { name: label })
    expect(button.className.split(' ').sort()).toEqual(['ha-link', ...(tone ? [tone] : [])].sort())
    expect(button).toHaveAttribute('title', label)
    expect(button.id).toBe('ws-button')
    expect(button.querySelector('svg.icon')).toBeTruthy()
  })

  it('reconnects on a click while not connected, and does nothing once connected', () => {
    ws.state = 'error'
    const { unmount } = render(<WebSocketIndicator />)
    fireEvent.click(screen.getByRole('button'))
    expect(ws.connect).toHaveBeenCalledTimes(1)
    unmount()
    ws.state = 'connected'
    render(<WebSocketIndicator />)
    fireEvent.click(screen.getByRole('button'))
    expect(ws.connect).toHaveBeenCalledTimes(1)
  })
})
