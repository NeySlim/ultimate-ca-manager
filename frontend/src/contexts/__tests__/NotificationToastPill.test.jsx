/**
 * Toasts as the mockup's toast(): one line at the bottom centre (#toast, always mounted so each message
 * is announced). A passing message is the inverted pill, alone; one that stays, or carries an action,
 * is the framed failure line with its icon, its action and Fermer le message. A newer message takes
 * the line; an older one still running comes back when it ends. Lines kept, errors announced assertively.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'

import { NotificationProvider, useNotification } from '../NotificationContext'

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

const line = () => document.getElementById('toast')

describe('toast: the inverted pill', () => {
  it('is the mockup\'s single line, in the scope of its rules, empty and hidden at rest', () => {
    expect(line()).toHaveAttribute('role', 'status')
    expect(line().parentElement).toHaveClass('atl', 'atl-island')
    expect(line()).not.toHaveClass('visible')
    expect(line()).toBeEmptyDOMElement()
  })

  it('shows a passing message alone: no icon, no button, five seconds', async () => {
    await act(async () => { api.showSuccess('Connection restored.') })
    expect(line()).toHaveClass('visible')
    expect(line()).not.toHaveClass('failure')
    expect(line().textContent).toBe('Connection restored.')
    expect(line().querySelector('svg')).toBeNull()
    expect(within(line()).queryAllByRole('button')).toHaveLength(0)
    await act(async () => { await vi.advanceTimersByTimeAsync(6000) })
    expect(screen.queryByText('Connection restored.')).toBeNull()
    expect(line()).not.toHaveClass('visible')
  })

  it('keeps every line of a long error', async () => {
    await act(async () => { api.showError('Import failed.\nLine 3: not a certificate.') })
    expect(line().textContent).toBe('Import failed.\nLine 3: not a certificate.')
  })

  it('announces an error assertively and other messages politely', async () => {
    await act(async () => { api.showError('Saving failed.') })
    expect(line()).toHaveAttribute('aria-live', 'assertive')
    await act(async () => { api.showInfo('Saved.') })
    expect(line()).toHaveAttribute('aria-live', 'polite')
  })

  it('shows the newer message, then the older one still running when the newer ends', async () => {
    await act(async () => { api.showError('Publication failed.', 0) })
    await act(async () => { api.showSuccess('Saved.', 1000) })
    expect(line().textContent).toBe('Saved.')
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(line()).toHaveTextContent('Publication failed.')
  })

  it('closes on Escape outside a dialog', async () => {
    await act(async () => { api.showSuccess('Saved.') })
    await act(async () => { fireEvent.keyDown(document.body, { key: 'Escape' }) })
    expect(screen.queryByText('Saved.')).toBeNull()
  })
})

describe('toast: the framed line that stays', () => {
  it('keeps the action of a message as its button, until it is used', async () => {
    const onClick = vi.fn()
    await act(async () => { api.showError('Publication failed.', { action: { label: 'Retry', onClick } }) })
    expect(line()).toHaveClass('visible', 'failure', 'tone-bad')
    expect(line().querySelector('.toast-msg svg.icon')).not.toBeNull()
    expect(within(line()).getByRole('button', { name: 'common.closeMessage' })).toHaveAttribute('id', 'toast-close')
    await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
    const retry = within(line()).getByRole('button', { name: 'Retry' })
    expect(retry).toHaveAttribute('id', 'toast-retry')
    await act(async () => { fireEvent.click(retry) })
    expect(onClick).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Publication failed.')).toBeNull()
  })

  it('takes the tone of its type: a persistent warning has the warning rule', async () => {
    await act(async () => { api.showWarning('Three certificates expire.', 0) })
    expect(line()).toHaveClass('failure', 'tone-warn')
  })

  it('closes with Fermer le message', async () => {
    await act(async () => { api.showInfo('Restart needed.', 0) })
    await act(async () => { fireEvent.click(within(line()).getByRole('button', { name: 'common.closeMessage' })) })
    expect(screen.queryByText('Restart needed.')).toBeNull()
  })

  it('still accepts the duration as a number', async () => {
    await act(async () => { api.showInfo('Short one.', 1000) })
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(screen.queryByText('Short one.')).toBeNull()
  })
})
