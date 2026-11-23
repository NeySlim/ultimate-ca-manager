/**
 * The palette of the mockup (app.js commandResults, M:1305, M:741, M:1437): every page of the menu the
 * account may open, « Émettre » that opens the issue form, and the ACME accounts and SCEP profiles found.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  openEntity: vi.fn(), navigate: vi.fn(), globalSearch: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, fallback) => (typeof fallback === 'string' ? fallback : key), i18n: { language: 'en' } }),
}))
vi.mock('react-router-dom', () => ({ useNavigate: () => mocks.navigate }))
vi.mock('../../hooks/useOpenEntity', () => ({ useOpenEntity: () => mocks.openEntity }))
vi.mock('../../hooks', () => ({
  useAllRecentHistory: () => ({ allRecent: [], refreshHistory: vi.fn() }),
  useAllFavorites: () => ({ allFavorites: [], refreshFavorites: vi.fn() }),
}))
vi.mock('../../services', () => ({ searchService: { globalSearch: mocks.globalSearch } }))

import { CommandPalette } from '../CommandPalette'

const can = (permissions) => ({
  isAdmin: () => permissions.includes('*'),
  hasPermission: (p) => permissions.includes('*') || permissions.includes(p),
})
const names = () => [...document.querySelectorAll('.command-result .name')].map((n) => n.textContent)

describe('CommandPalette, the mockup palette', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.globalSearch.mockResolvedValue({
      certificates: [], cas: [], users: [], templates: [],
      acme_accounts: [{ id: 4, name: 'ops@example.com', account_id: 'abc', status: 'valid' }],
      scep_profiles: [{ id: 2, name: 'Phones', url_slug: 'phones', enabled: true }],
    })
  })

  it('lists the pages the menu had and the palette lacked', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />)
    for (const key of ['shell.moduleLabel.truststore', 'userCertificates.title', 'common.tsa',
      'shell.moduleLabel.crlOcsp', 'common.keyRecovery', 'shell.moduleLabel.discovery', 'common.systemLogs']) {
      expect(names(), key).toContain(key)
    }
  })

  it('lists only what the account may open: no admin page, no action it may not run', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} can={can(['read:certificates', 'read:truststore'])} />)
    expect(names()).toContain('shell.moduleLabel.truststore')
    expect(names()).toContain('shell.moduleLabel.discovery')
    for (const key of ['common.systemLogs', 'common.users', 'common.keyRecovery', 'common.tsa',
      'commands.actions.newCertificate', 'commands.actions.newCA', 'commands.actions.uploadCSR']) {
      expect(names(), key).not.toContain(key)
    }
  })

  it.each([
    ['commands.actions.newCertificate', '/certificates?action=create'],
    ['commands.actions.newCA', '/cas?action=create'],
    ['commands.actions.uploadCSR', '/csrs?action=upload'],
  ])('%s opens its form on its page', (label, to) => {
    const onOpenChange = vi.fn()
    render(<CommandPalette open onOpenChange={onOpenChange} can={can(['*'])} />)
    fireEvent.click(screen.getByText(label))
    expect(mocks.navigate).toHaveBeenCalledWith(to)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('finds the ACME accounts and SCEP profiles, named by their type, each opening in its page', async () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />)
    fireEvent.change(screen.getByPlaceholderText('commandPalette.searchPlaceholder'), { target: { value: 'ph' } })
    const account = (await screen.findByText('ops@example.com')).closest('button')
    expect(account.querySelector('.hint').textContent).toBe('commandPalette.acmeAccount')
    expect(account.querySelector('svg, .icon, [data-icon]')).not.toBeNull()
    const profile = screen.getByText('Phones').closest('button')
    expect(profile.querySelector('.hint').textContent).toBe('commandPalette.scepProfile')
    fireEvent.click(account)
    expect(mocks.navigate).toHaveBeenLastCalledWith('/acme?item=4')
    fireEvent.click(profile)
    expect(mocks.navigate).toHaveBeenLastCalledWith('/scep-config?item=2')
    expect(mocks.openEntity).not.toHaveBeenCalled()
  })
})
