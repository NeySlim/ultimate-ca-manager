/**
 * The confirmation dialog as the mockup's: the safe action takes the focus, a destructive
 * action is announced in the warning notice, an acknowledge-only dialog focuses its one button.
 */
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))

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

const ask = async (message, options) => {
  render(<NotificationProvider><Probe /></NotificationProvider>)
  await act(async () => { api.showConfirm(message, options) })
  return screen.findByTestId('confirm-dialog')
}

describe('confirmation dialog', () => {
  it('puts the focus on Cancel, the safe action', async () => {
    await ask('Export the selection?')
    expect(screen.getByRole('button', { name: 'common.cancel' })).toHaveFocus()
  })

  it('says a destructive action in the warning notice, with its icon', async () => {
    const dialog = await ask('The account can no longer order.', { variant: 'danger', confirmText: 'Deactivate' })
    const notice = dialog.querySelector('.ui-notice.is-warn')
    expect(notice).toHaveTextContent('The account can no longer order.')
    expect(notice.querySelector('svg')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'common.cancel' })).toHaveFocus()
  })

  it('keeps the plain message for an ordinary confirmation', async () => {
    const dialog = await ask('Export the selection?')
    expect(dialog.querySelector('.ui-notice')).toBeNull()
    expect(dialog.querySelector('.ui-dialog-message')).toHaveTextContent('Export the selection?')
  })

  it('focuses the only button of an acknowledge-only dialog', async () => {
    await ask('Restart the service.', { cancelText: null, confirmText: 'Understood' })
    expect(screen.getByRole('button', { name: 'Understood' })).toHaveFocus()
  })
})
