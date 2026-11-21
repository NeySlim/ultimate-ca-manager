/**
 * DUP-FE-006 — the Cancel-button escape hatch in the confirm dialog.
 *
 * `showConfirm(msg, { cancelText: null })` is supposed to render an
 * acknowledge-only dialog: the render guard is `cancelText !== null`. It could
 * never fire, because the option was normalised with `||`, which turns an
 * explicit `null` back into 'Cancel'. These tests pin both halves: the escape
 * hatch works, and the 59 call sites that pass nothing (or a real string) are
 * unaffected.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen, act } from '@testing-library/react'

beforeAll(() => {
  global.ResizeObserver = class ResizeObserver {
    constructor(cb) { this._cb = cb }
    observe() {}
    unobserve() {}
    disconnect() {}
  }
})

vi.mock('@radix-ui/react-dialog', () => ({
  Root: ({ children, open }) => (open ? <div>{children}</div> : null),
  Trigger: ({ children }) => <div>{children}</div>,
  Portal: ({ children }) => <div>{children}</div>,
  Overlay: ({ children }) => <div>{children}</div>,
  Content: ({ children }) => <div>{children}</div>,
  Title: ({ children }) => <div>{children}</div>,
  Description: ({ children }) => <div>{children}</div>,
  Close: ({ children }) => <div>{children}</div>,
}))

// The default buttons are translated: English strings stand in for the catalogue.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k) => ({ 'common.cancel': 'Cancel', 'common.confirm': 'Confirm' }[k] ?? k) }),
}))

import { NotificationProvider, useNotification } from '../NotificationContext'

let api
function Probe() {
  api = useNotification()
  return null
}

function renderProvider() {
  api = null
  render(
    <NotificationProvider>
      <Probe />
    </NotificationProvider>,
  )
}

/** Text of every labelled <button> on screen (the close cross of the dialog has none). */
function buttonLabels() {
  return screen.queryAllByRole('button').map((b) => b.textContent.trim()).filter(Boolean)
}

describe('showConfirm — cancelText: null hides the Cancel button', () => {
  it('renders only the confirm button when cancelText is explicitly null', async () => {
    renderProvider()
    await act(async () => {
      api.showConfirm('Acknowledge this?', { confirmText: 'Got it', cancelText: null })
    })

    expect(buttonLabels()).toEqual(['Got it'])
    expect(screen.queryByText('Cancel')).toBeNull()
  })

  it('still renders Cancel when no cancelText is passed (the 58 default call sites)', async () => {
    renderProvider()
    await act(async () => {
      api.showConfirm('Delete this?', { confirmText: 'Delete' })
    })

    expect(buttonLabels()).toEqual(['Cancel', 'Delete'])
  })

  it('still renders a caller-supplied cancelText (the 2 call sites that pass one)', async () => {
    renderProvider()
    await act(async () => {
      api.showConfirm('Delete this?', { confirmText: 'Delete', cancelText: 'Annuler' })
    })

    expect(buttonLabels()).toEqual(['Annuler', 'Delete'])
  })

  it('an empty-string cancelText still falls back to Cancel, as before', async () => {
    // `??` only special-cases null/undefined, so '' keeps hitting the
    // `|| 'Cancel'` default at the render site — unchanged behaviour.
    renderProvider()
    await act(async () => {
      api.showConfirm('Delete this?', { confirmText: 'Delete', cancelText: '' })
    })

    expect(buttonLabels()).toEqual(['Cancel', 'Delete'])
  })

  it('the promise still resolves true/false in the acknowledge-only dialog', async () => {
    renderProvider()
    let resolved
    await act(async () => {
      api.showConfirm('Acknowledge this?', { confirmText: 'Got it', cancelText: null })
        .then((r) => { resolved = r })
    })

    const confirmBtn = screen.getByText('Got it')
    await act(async () => { confirmBtn.click() })
    expect(resolved).toBe(true)
  })
})
