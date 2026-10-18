/**
 * The package stops UCM while it rebuilds its Python environment, about five
 * minutes with UCM_FIPS_BUILD=1: the update overlay must keep waiting that long,
 * while a plain restart still gives up after three minutes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, renderHook, screen } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), showConfirm: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, values) => (values?.minutes ? `${key}:${values.minutes}` : key) }),
}))
vi.mock('../../services', () => ({ apiClient: { get: mocks.get, post: mocks.post } }))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: mocks.showConfirm }),
}))
// The hooks index pulls in AuthContext and i18n; only this hook is used
vi.mock('../../hooks', () => vi.importActual('../../hooks/useServiceReconnect'))
vi.mock('../index.js', async () => {
  const { ServiceReconnectOverlay } = await vi.importActual('../ServiceReconnectOverlay')
  return {
    Card: ({ children }) => <div>{children}</div>,
    Button: ({ children, ...props }) => <button {...props}>{children}</button>,
    Badge: ({ children }) => <span>{children}</span>,
    LoadingSpinner: () => null,
    ServiceReconnectOverlay,
  }
})

import { UpdateChecker } from '../UpdateChecker'
import { useServiceReconnect } from '../../hooks/useServiceReconnect'

const tick = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })
const MINUTE = 60 * 1000
const health = { down: true }

function fakeHealth() {
  globalThis.fetch = vi.fn(async () => {
    if (health.down) throw new TypeError('Failed to fetch')
    return { ok: true, json: async () => ({ started_at: 200, version: '2.242', websocket: true }) }
  })
}

describe('waiting for UCM after an update', () => {
  const realFetch = globalThis.fetch
  beforeEach(() => {
    vi.useFakeTimers()
    health.down = true
    fakeHealth()
    mocks.get.mockResolvedValue({
      data: { update_available: true, can_auto_update: true, download_url: 'x', latest_version: '2.242', current_version: '2.241' },
    })
    mocks.post.mockResolvedValue({})
    mocks.showConfirm.mockResolvedValue(true)
  })
  afterEach(() => {
    vi.useRealTimers()
    globalThis.fetch = realFetch
  })

  it('keeps waiting through a FIPS rebuild, with the reason on screen', async () => {
    render(<UpdateChecker />)
    await tick(0)
    fireEvent.click(screen.getByText('Install Update'))
    await tick(0)
    expect(mocks.post).toHaveBeenCalledWith('/system/updates/install', expect.anything())
    expect(screen.getByText('reconnect.updateNote:10')).toBeInTheDocument()

    await tick(MINUTE + 9 * MINUTE)
    expect(screen.getByText('reconnect.connecting')).toBeInTheDocument()
    expect(screen.queryByText('reconnect.timeout')).toBeNull()

    health.down = false
    await tick(3000)
    expect(screen.getByText('reconnect.redirecting')).toBeInTheDocument()
  })

  it('stops polling once the page is left', async () => {
    const { result, unmount } = renderHook(() => useServiceReconnect())
    act(() => { result.current.waitForRestart() })
    await tick(MINUTE + 10 * 1000)
    const calls = globalThis.fetch.mock.calls.length
    expect(calls).toBeGreaterThan(1)
    unmount()
    health.down = false
    await tick(10 * MINUTE)
    expect(globalThis.fetch.mock.calls.length).toBe(calls)
  })

  it('a plain restart still times out after three minutes', async () => {
    const { result } = renderHook(() => useServiceReconnect())
    act(() => { result.current.waitForRestart() })
    await tick(MINUTE + 2.5 * MINUTE)
    expect(result.current.status).toBe('connecting')
    await tick(MINUTE)
    expect(result.current.status).toBe('timeout')
  })
})
