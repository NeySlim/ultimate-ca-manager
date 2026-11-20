/**
 * Toasts in the mockup's grammar: a passing message is the inverted pill (no icon, no button);
 * one that stays, or carries an action, is the framed failure line with its action and a close
 * button. A message keeps its line breaks and an error is announced assertively.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'

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

const toastOf = (text) => screen.getByText(text).closest('li')

describe('toast: the inverted pill', () => {
  it('shows a passing message alone: no icon, no button, five seconds', async () => {
    await act(async () => { api.showSuccess('Connection restored.') })
    const toast = toastOf('Connection restored.')
    expect(toast).toHaveClass('ui-toast')
    expect(toast).not.toHaveClass('is-held')
    expect(toast.querySelector('svg')).toBeNull()
    expect(within(toast).queryAllByRole('button')).toHaveLength(0)
    await act(async () => { await vi.advanceTimersByTimeAsync(6000) })
    expect(screen.queryByText('Connection restored.')).toBeNull()
  })

  it('keeps every line of a long error, in the pill text', async () => {
    await act(async () => { api.showError('Import failed.\nLine 3: not a certificate.') })
    const text = screen.getByText(/Import failed\./)
    expect(text.textContent).toBe('Import failed.\nLine 3: not a certificate.')
    expect(text).toHaveClass('ui-toast-text')
  })

  it('announces an error assertively and other messages politely', async () => {
    await act(async () => { api.showError('Saving failed.') })
    await act(async () => { api.showInfo('Saved.') })
    await act(async () => { await vi.advanceTimersByTimeAsync(50) })
    const live = (text) => [...document.querySelectorAll('[aria-live]')].find(el => el.textContent.includes(text))?.getAttribute('aria-live')
    expect(live('Saving failed.')).toBe('assertive')
    expect(live('Saved.')).toBe('polite')
  })
})

describe('toast: the framed line that stays', () => {
  it('keeps the action of a message as its button, until it is used', async () => {
    const onClick = vi.fn()
    await act(async () => { api.showError('Publication failed.', { action: { label: 'Retry', onClick } }) })
    const toast = toastOf('Publication failed.')
    expect(toast).toHaveClass('ui-toast', 'is-held', 'is-error')
    expect(toast.querySelector('svg.ui-toast-icon')).not.toBeNull()
    expect(within(toast).getByRole('button', { name: 'common.closeMessage' })).toBeInTheDocument()
    await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
    await act(async () => { fireEvent.click(within(toastOf('Publication failed.')).getByRole('button', { name: 'Retry' })) })
    expect(onClick).toHaveBeenCalledTimes(1)
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(screen.queryByText('Publication failed.')).toBeNull()
  })

  it('takes the tone of its type: a persistent warning has the warning rule', async () => {
    await act(async () => { api.showWarning('Three certificates expire.', 0) })
    expect(toastOf('Three certificates expire.')).toHaveClass('is-held', 'is-warning')
  })

  it('still accepts the duration as a number', async () => {
    await act(async () => { api.showInfo('Short one.', 1000) })
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(screen.queryByText('Short one.')).toBeNull()
  })
})
