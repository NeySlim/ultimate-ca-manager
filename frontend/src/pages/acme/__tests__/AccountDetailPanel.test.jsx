import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  patch: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  hasPermission: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../services', () => ({
  apiClient: { patch: mocks.patch },
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError }),
}))

vi.mock('../../../hooks', async () => ({
  usePersistedState: (await vi.importActual('../../../hooks/usePersistedState')).usePersistedState,
  useClipboard: () => ({ copy: vi.fn() }),
  usePermission: () => ({ hasPermission: mocks.hasPermission }),
}))
vi.mock('../../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))

import AccountDetailPanel from '../AccountDetailPanel'
import { KEY_ALGORITHMS } from '../../../lib/keyAlgorithms'

const account = {
  id: 7,
  account_id: 'acme-1234567890abcdef',
  status: 'valid',
  contact: ['mailto:old@example.com'],
  key_type: 'EC-P256',
  created_at: '2026-01-01T00:00:00Z',
}

// The account's dock (the mockup's acmeAccountPanel), opened on its Compte tab
const renderPanel = (props = {}) => render(
  <AccountDetailPanel
    account={account}
    orders={[]}
    challenges={[]}
    section="account"
    onSection={vi.fn()}
    onClose={vi.fn()}
    onDeactivate={vi.fn()}
    onDelete={vi.fn()}
    {...props}
  />
)
const emailDraft = () => screen.getByLabelText('common.email')

describe('AccountDetailPanel email edit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.hasPermission.mockReturnValue(true)
  })

  it('renders the current email in the account properties', () => {
    renderPanel()
    expect(screen.getByText(/mailto:old@example.com/)).toBeInTheDocument()
  })

  it('shows an explicit edit action instead of an icon-only control', () => {
    renderPanel()
    expect(screen.getByRole('button', { name: 'acme.editEmail' })).toHaveTextContent('acme.editEmail')
  })

  it('saves the new email through the API and notifies the parent immediately', async () => {
    mocks.patch.mockResolvedValue({ data: { contact: ['mailto:new@example.com'] } })
    const onChanged = vi.fn()
    renderPanel({ onChanged })

    fireEvent.click(screen.getByRole('button', { name: 'acme.editEmail' }))
    fireEvent.change(emailDraft(), { target: { value: 'new@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))

    await vi.waitFor(() => expect(mocks.patch).toHaveBeenCalledWith(
      '/acme/accounts/acme-1234567890abcdef', { email: 'new@example.com' }
    ))
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({
      contact: ['mailto:new@example.com'],
    }))
    expect(mocks.showSuccess).toHaveBeenCalled()
  })

  it('hides the edit button without write:acme', () => {
    mocks.hasPermission.mockImplementation((p) => p !== 'write:acme')
    renderPanel()
    expect(screen.queryByRole('button', { name: 'acme.editEmail' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('common.email')).not.toBeInTheDocument()
  })

  it('shows the RFC 8555 caveat while editing', () => {
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: 'acme.editEmail' }))
    expect(screen.getByText('acme.editEmailCaveat')).toBeInTheDocument()
  })
})

describe('AccountDetailPanel deactivation', () => {
  beforeEach(() => mocks.hasPermission.mockReturnValue(true))

  it('asks the mockup question before deactivating, never on its own', async () => {
    const onDeactivate = vi.fn().mockResolvedValue()
    renderPanel({ onDeactivate })
    fireEvent.click(screen.getByRole('button', { name: 'acme.disableAccount' }))
    expect(onDeactivate).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog', { name: 'acme.disableTitle' })).toHaveTextContent('acme.disableWarning')
    fireEvent.click(screen.getByRole('button', { name: 'acme.disableConfirm' }))
    await vi.waitFor(() => expect(onDeactivate).toHaveBeenCalledWith(7))
  })

  it('offers no deactivation for a deactivated account, and says it is final', () => {
    renderPanel({ account: { ...account, status: 'deactivated' } })
    expect(screen.queryByRole('button', { name: 'acme.disableAccount' })).toBeNull()
    expect(screen.getByText('acme.deactivationFinal')).toBeInTheDocument()
  })
})

describe('AccountDetailPanel key type', () => {
  beforeEach(() => mocks.hasPermission.mockReturnValue(true))

  it('shows the key type the account carries', () => {
    renderPanel()
    expect(screen.getAllByText(account.key_type).length).toBeGreaterThanOrEqual(1)
  })

  // The API sends key_type null for a JWK it cannot read: no label is guessed
  it('names no key type for an account that carries none', () => {
    renderPanel({ account: { ...account, key_type: null } })
    expect(KEY_ALGORITHMS.filter(row => screen.queryAllByText(row.label).length)).toEqual([])
  })
})
