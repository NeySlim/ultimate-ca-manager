/** The wait for a restarted service in the mockup's narrow modal(): its state, its progress, Refresh and Cancel once it times out. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, a, b) => { const o = typeof a === 'object' ? a : b; return o && (o.seconds ?? o.count) !== undefined ? `${key}:${o.seconds ?? o.count}` : key } }),
}))

import { ServiceReconnectOverlay } from '../ServiceReconnectOverlay'

const dialog = () => screen.getByTestId('service-reconnect')

describe('ServiceReconnectOverlay', () => {
  it('is the mockup\'s narrow dialog with the state and the countdown as a progress bar', () => {
    render(<ServiceReconnectOverlay status="countdown" countdown={45} note="NOTE" />)
    expect(dialog().tagName).toBe('DIALOG')
    expect(dialog()).toHaveClass('narrow')
    expect(within(dialog()).getByRole('heading', { level: 2 })).toHaveTextContent('reconnect.countdown')
    expect(dialog().querySelector('.modal-head p')).toHaveTextContent('reconnect.countdownSub:45')
    expect(dialog().querySelector('.progress span').style.width).toBe('25%')
    expect(dialog()).toHaveTextContent('NOTE')
    expect(document.querySelector('.fixed')).toBeNull()
  })

  it('counts the attempts while it reconnects', () => {
    render(<ServiceReconnectOverlay status="connecting" attempt={3} />)
    expect(dialog().querySelector('.progress span').style.width).toBe('10%')
    expect(dialog()).toHaveTextContent('reconnect.attempt:3')
  })

  it('offers Refresh and Cancel once it times out', () => {
    const onCancel = vi.fn()
    const reload = vi.fn()
    vi.stubGlobal('location', { reload })
    render(<ServiceReconnectOverlay status="timeout" onCancel={onCancel} />)
    const actions = dialog().querySelector('.modal-actions')
    fireEvent.click(within(actions).getByRole('button', { name: 'reconnect.refresh' }))
    expect(reload).toHaveBeenCalled()
    fireEvent.click(within(actions).getByRole('button', { name: 'common.cancel' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    vi.unstubAllGlobals()
  })

  it('has no actions while it waits', () => {
    render(<ServiceReconnectOverlay status="redirecting" onCancel={vi.fn()} />)
    expect(dialog().querySelector('.modal-actions')).toBeNull()
    expect(within(dialog()).getByRole('heading', { level: 2 })).toHaveTextContent('reconnect.redirecting')
  })

  it('cancels the wait when closed from its head, as Cancel does', () => {
    const onCancel = vi.fn()
    render(<ServiceReconnectOverlay status="connecting" attempt={1} onCancel={onCancel} />)
    fireEvent.click(within(dialog()).getByRole('button', { name: 'common.closeWindow' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
