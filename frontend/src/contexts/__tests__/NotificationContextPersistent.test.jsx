/**
 * A toast shown with a duration of 0 stays until the user closes it: neither the context's
 * timer nor the toast library's own default duration takes it away. Others still go at 5 s.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'

import { NotificationProvider, useNotification } from '../NotificationContext'

beforeAll(() => {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
})

let api
function Probe() {
  api = useNotification()
  return null
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  render(<NotificationProvider><Probe /></NotificationProvider>)
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('NotificationContext: a persistent toast', () => {
  it('keeps a toast of duration 0 until it is closed', async () => {
    await act(async () => { api.showError('Restart the application before using it.', 0) })
    await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
    const toast = screen.getByText('Restart the application before using it.')
    const close = toast.closest('#toast').querySelector('#toast-close')
    await act(async () => { fireEvent.click(close) })
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(screen.queryByText('Restart the application before using it.')).toBeNull()
  })

  it('still takes a default toast away after 5 s', async () => {
    await act(async () => { api.showError('Saved, but not everywhere') })
    expect(screen.getByText('Saved, but not everywhere')).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(6000) })
    expect(screen.queryByText('Saved, but not everywhere')).toBeNull()
  })
})
