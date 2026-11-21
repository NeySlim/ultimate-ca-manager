/** Editing a CA account: the default cannot be unticked and the key algorithm is not editable. */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }), useMobile: () => ({ isMobile: false }) }))
vi.mock('../DnsUpdateKeysPanel', () => ({ default: () => null }))

import CaAccountsManager from '../CaAccountsManager'
import { WithDockSlot } from '../../protocols/__tests__/withDockSlot'
import { blockedWhileSuspended } from '../../../components/shell/__tests__/writeGuardProbe'

const account = (extra = {}) => ({
  id: 1, label: 'Actalis', directory_url: 'https://ca.example/dir', email: 'a@example.com',
  account_key_algorithm: 'ES384', is_default: false, is_registered: true, ...extra,
})

const edit = async (acct, onUpdate = vi.fn().mockResolvedValue({})) => {
  const user = userEvent.setup()
  render(<WithDockSlot><CaAccountsManager accounts={[acct]} canWrite canDelete onUpdate={onUpdate} /></WithDockSlot>)
  await user.click(screen.getByRole('button', { name: 'Actalis' }))
  await user.click(await screen.findByRole('button', { name: /common.edit/ }))
  return { user, onUpdate }
}

describe('CaAccountsManager edit form', () => {
  it('disables the default box of the default account and says why', async () => {
    await edit(account({ is_default: true }))
    expect(screen.getByRole('checkbox', { name: /acme.useAsDefault/ })).toBeDisabled()
    expect(screen.getByText('acme.defaultChooseAnother')).toBeInTheDocument()
  })

  it('leaves the default box of another account editable', async () => {
    await edit(account())
    expect(screen.getByRole('checkbox', { name: /acme.useAsDefault/ })).toBeEnabled()
    expect(screen.queryByText('acme.defaultChooseAnother')).not.toBeInTheDocument()
  })

  it('does not send the algorithm back', async () => {
    const { user, onUpdate } = await edit(account())
    expect(screen.getByText('acme.accountKeyFixed')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'common.save' }))
    expect(onUpdate).toHaveBeenCalled()
    expect(onUpdate.mock.calls[0][1]).not.toHaveProperty('account_key_algorithm')
  })
})

describe('CaAccountsManager write guard', () => {
  it('suspends Set as default and Edit with the other writes', async () => {
    render(<WithDockSlot><CaAccountsManager accounts={[account()]} canWrite canDelete onUpdate={vi.fn()} onSetDefault={vi.fn()} /></WithDockSlot>)
    screen.getByRole('button', { name: 'Actalis' }).click()
    expect(blockedWhileSuspended(await screen.findByRole('button', { name: /acme.setDefault/ }))).toBe(true)
    expect(blockedWhileSuspended(screen.getByRole('button', { name: /common.edit/ }))).toBe(true)
  })
})
