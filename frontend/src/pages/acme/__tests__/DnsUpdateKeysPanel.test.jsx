/**
 * DNS UPDATE (RFC 2136) keys of a proxy account: list, create with the secret
 * shown once, revoke and delete, and the client snippets in the "shown once" dialog.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  remove: vi.fn(),
  listEab: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showConfirm: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../../services', () => ({
  acmeService: {
    listDnsUpdateKeys: mocks.list,
    createDnsUpdateKey: mocks.create,
    deleteDnsUpdateKey: mocks.remove,
    listEabCredentials: mocks.listEab,
  },
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({
    showSuccess: mocks.showSuccess,
    showError: mocks.showError,
    showConfirm: mocks.showConfirm,
  }),
}))

vi.mock('../../../hooks', () => ({
  useClipboard: () => ({ copy: vi.fn() }),
}))

// The Radix select does not open in jsdom: a native select keeps the form testable.
vi.mock('../../../components', async (importOriginal) => ({
  ...(await importOriginal()),
  Select: ({ label, value, onChange, options }) => (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import { effectiveDnsUpdatePort } from '../dnsUpdatePort'
import DnsUpdateKeysPanel from '../DnsUpdateKeysPanel'

const ACCOUNT = { id: 7, label: 'Actalis', proxy_slug: 'actalis' }
const SECRET = 'c2VjcmV0LXZhbHVlLW9ubHktb25jZQ=='

const key = (id, extra = {}) => ({
  id, acme_client_account_id: 7, eab_credential_id: null, name: `key${id}.example.`,
  algorithm: 'hmac-sha256', status: 'active', created_at: '2026-10-01T00:00:00Z',
  last_used_at: null, revoked_at: null, notes: null, ...extra,
})

const renderPanel = (props = {}) => render(
  <DnsUpdateKeysPanel account={ACCOUNT} proxyPublicBase="https://ucm.lan:8443/acme/proxy"
    dnsUpdatePort={8053} canWrite canDelete {...props} />,
)

const createKey = async (user, response, pick = async () => {}) => {
  mocks.create.mockResolvedValue({ data: { ...key(9, response), secret: SECRET } })
  await user.click(await screen.findByRole('button', { name: /acme.dnsUpdate.create/ }))
  const dialog = await screen.findByRole('dialog')
  await pick(within(dialog))
  await user.click(within(dialog).getByRole('button', { name: 'acme.dnsUpdate.generate' }))
}

describe('DnsUpdateKeysPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.list.mockResolvedValue({ data: [] })
    mocks.listEab.mockResolvedValue({ data: [
      { id: 3, label: 'ci-runner', kid: 'kid-3', status: 'active' },
      { id: 4, label: 'old', kid: 'kid-4', status: 'revoked' },
    ] })
    mocks.remove.mockResolvedValue({})
    mocks.showConfirm.mockResolvedValue(true)
  })

  it('lists the keys with algorithm, status, EAB link and last use', async () => {
    mocks.list.mockResolvedValue({ data: [
      key(1, { eab_credential_id: 3, last_used_at: '2026-10-02T00:00:00Z' }),
      key(2, { algorithm: 'hmac-sha512', status: 'revoked' }),
    ] })
    renderPanel()
    const first = within(await screen.findByTestId('dns-update-key-1'))
    expect(first.getByText('key1.example.')).toBeInTheDocument()
    expect(first.getByText('hmac-sha256')).toBeInTheDocument()
    expect(first.getByText('acme.dnsUpdate.statusActive')).toBeInTheDocument()
    expect(await first.findByText('ci-runner')).toBeInTheDocument()
    expect(first.queryByText(/acme.dnsUpdate.never/)).not.toBeInTheDocument()
    const second = within(screen.getByTestId('dns-update-key-2'))
    expect(second.getByText('hmac-sha512')).toBeInTheDocument()
    expect(second.getByText('acme.dnsUpdate.statusRevoked')).toBeInTheDocument()
    expect(mocks.list).toHaveBeenCalledWith(7)
  })

  it('creates a key with the chosen algorithm and EAB credential and shows the secret once', async () => {
    const user = userEvent.setup()
    renderPanel()
    await createKey(user, { algorithm: 'hmac-sha512', eab_credential_id: 3 }, async (dialog) => {
      await user.selectOptions(dialog.getByLabelText('acme.dnsUpdate.algorithm'), 'hmac-sha512')
      // The revoked credential is not offered
      expect(dialog.queryByRole('option', { name: 'old' })).not.toBeInTheDocument()
      await user.selectOptions(dialog.getByLabelText('acme.dnsUpdate.eabCredential'), '3')
    })
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith(7, {
      algorithm: 'hmac-sha512', eab_credential_id: 3,
    }))
    expect(await screen.findByTestId('dns-update-created-secret')).toHaveTextContent(SECRET)
    expect(screen.getByTestId('dns-update-created-name')).toHaveTextContent('key9.example.')
    expect(screen.getByTestId('dns-update-created-algorithm')).toHaveTextContent('hmac-sha512')
    expect(screen.getByText('acme.dnsUpdate.secretWarningTitle')).toBeInTheDocument()
  })

  it('sends the typed name and notes, and leaves them out when empty', async () => {
    const user = userEvent.setup()
    renderPanel()
    await createKey(user, {}, async (dialog) => {
      await user.type(dialog.getByLabelText('acme.dnsUpdate.name'), 'web01.example')
      await user.type(dialog.getByLabelText('acme.dnsUpdate.notes'), 'lego on web01')
    })
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith(7, {
      algorithm: 'hmac-sha256', name: 'web01.example', notes: 'lego on web01',
    }))
  })

  it('does not keep the secret in the page after the dialog is closed', async () => {
    const user = userEvent.setup()
    renderPanel()
    await createKey(user, {})
    expect(await screen.findByTestId('dns-update-created-secret')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'acme.dnsUpdate.secretConfirm' }))
    await waitFor(() => expect(screen.queryByTestId('dns-update-created-secret')).not.toBeInTheDocument())
    expect(document.body.textContent).not.toContain(SECRET)
  })

  it('shows an error and no secret dialog when the create call fails', async () => {
    const user = userEvent.setup()
    mocks.create.mockRejectedValue(new Error('A key with this name already exists'))
    renderPanel()
    await user.click(await screen.findByRole('button', { name: /acme.dnsUpdate.create/ }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'acme.dnsUpdate.generate' }))
    await waitFor(() => expect(mocks.showError).toHaveBeenCalledWith('A key with this name already exists'))
    expect(screen.queryByTestId('dns-update-created-secret')).not.toBeInTheDocument()
  })

  it('revokes an active key and deletes a revoked one with the same service call', async () => {
    const user = userEvent.setup()
    mocks.list.mockResolvedValue({ data: [key(1), key(2, { status: 'revoked' })] })
    renderPanel()
    await user.click(within(await screen.findByTestId('dns-update-key-1')).getByTitle('acme.dnsUpdate.revoke'))
    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith(7, 1))
    expect(mocks.showConfirm).toHaveBeenCalledTimes(1)
    await user.click(within(screen.getByTestId('dns-update-key-2')).getByTitle('acme.dnsUpdate.delete'))
    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith(7, 2))
    expect(mocks.remove).toHaveBeenCalledTimes(2)
  })

  it('does not call the service when the confirmation is refused', async () => {
    const user = userEvent.setup()
    mocks.showConfirm.mockResolvedValue(false)
    mocks.list.mockResolvedValue({ data: [key(1)] })
    renderPanel()
    await user.click(within(await screen.findByTestId('dns-update-key-1')).getByTitle('acme.dnsUpdate.revoke'))
    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalled())
    expect(mocks.remove).not.toHaveBeenCalled()
  })

  it('hides create, revoke and delete without the permissions', async () => {
    mocks.list.mockResolvedValue({ data: [key(1), key(2, { status: 'revoked' })] })
    renderPanel({ canWrite: false, canDelete: false })
    await screen.findByTestId('dns-update-key-1')
    expect(screen.queryByRole('button', { name: /acme.dnsUpdate.create/ })).not.toBeInTheDocument()
    expect(screen.queryByTitle('acme.dnsUpdate.revoke')).not.toBeInTheDocument()
    expect(screen.queryByTitle('acme.dnsUpdate.delete')).not.toBeInTheDocument()
  })

  describe('snippets in the dialog', () => {
    const openTab = async (user, name) => {
      await user.click(await screen.findByRole('tab', { name }))
    }

    it('sets the algorithm in the cert-manager, certbot and lego snippets of a sha256 key', async () => {
      const user = userEvent.setup()
      renderPanel()
      await createKey(user, {})
      await screen.findByTestId('dns-update-created-secret')

      expect(screen.getByTestId('dns-update-snippet-bind')).toHaveTextContent('algorithm hmac-sha256;')
      await openTab(user, 'acme.dnsUpdate.tabCertbot')
      expect(screen.getByTestId('dns-update-snippet-certbot')).toHaveTextContent('dns_rfc2136_algorithm = HMAC-SHA256')
      expect(screen.getByTestId('dns-update-snippet-certbot')).toHaveTextContent('dns_rfc2136_port = 8053')
      await openTab(user, 'acme.dnsUpdate.tabLego')
      expect(screen.getByTestId('dns-update-snippet-lego')).toHaveTextContent('DNSUPDATE_TSIG_ALGORITHM="hmac-sha256."')
      await openTab(user, 'acme.dnsUpdate.tabCertManager')
      expect(screen.getByTestId('dns-update-snippet-certmanager')).toHaveTextContent('tsigAlgorithm: HMACSHA256')
      expect(screen.queryByTestId('dns-update-note-noteCertManagerSha384')).not.toBeInTheDocument()
    })

    it('shows the "not supported" note instead of a cert-manager snippet for a sha384 key', async () => {
      const user = userEvent.setup()
      renderPanel()
      await createKey(user, { algorithm: 'hmac-sha384' })
      await screen.findByTestId('dns-update-created-secret')
      await openTab(user, 'acme.dnsUpdate.tabCertManager')
      expect(screen.getByTestId('dns-update-note-noteCertManagerSha384')).toBeInTheDocument()
      expect(screen.queryByTestId('dns-update-snippet-certmanager')).not.toBeInTheDocument()
      // The other clients still get their snippet
      await openTab(user, 'acme.dnsUpdate.tabCertbot')
      expect(screen.getByTestId('dns-update-snippet-certbot')).toHaveTextContent('HMAC-SHA384')
    })

    it('uses port 53 and the disabled-listener note when the listener is off', async () => {
      const user = userEvent.setup()
      renderPanel({ dnsUpdatePort: 0 })
      await createKey(user, {})
      await screen.findByTestId('dns-update-created-secret')
      expect(screen.getByText('acme.dnsUpdate.notePortDisabled')).toBeInTheDocument()
      expect(screen.queryByText('acme.dnsUpdate.notePort')).not.toBeInTheDocument()
      await openTab(user, 'acme.dnsUpdate.tabLego')
      expect(screen.getByTestId('dns-update-snippet-lego')).toHaveTextContent('DNSUPDATE_NAMESERVER="ucm.lan:53"')
    })

    it('uses port 53 and the disabled note when the env value is invalid (effective port 0)', async () => {
      const user = userEvent.setup()
      const settings = { dns_update_port: 8053, dns_update_port_env: '70000', dns_update_port_effective: 0 }
      renderPanel({ dnsUpdatePort: effectiveDnsUpdatePort(settings) })
      await createKey(user, {})
      await screen.findByTestId('dns-update-created-secret')
      expect(screen.getByText('acme.dnsUpdate.notePortDisabled')).toBeInTheDocument()
      await openTab(user, 'acme.dnsUpdate.tabLego')
      expect(screen.getByTestId('dns-update-snippet-lego')).toHaveTextContent('DNSUPDATE_NAMESERVER="ucm.lan:53"')
    })

    it('uses the effective port 8053 in the note and the snippets', async () => {
      const user = userEvent.setup()
      const settings = { dns_update_port: 0, dns_update_port_env: '8053', dns_update_port_effective: 8053 }
      renderPanel({ dnsUpdatePort: effectiveDnsUpdatePort(settings) })
      await createKey(user, {})
      await screen.findByTestId('dns-update-created-secret')
      expect(screen.getByText('acme.dnsUpdate.notePort')).toBeInTheDocument()
      await openTab(user, 'acme.dnsUpdate.tabLego')
      expect(screen.getByTestId('dns-update-snippet-lego')).toHaveTextContent('DNSUPDATE_NAMESERVER="ucm.lan:8053"')
    })
  })
})
