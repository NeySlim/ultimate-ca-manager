/**
 * SCEP as the mockup's scep module draws it: the profiles list (Autorité, Modèle, Intune, État)
 * with its chips, the dock with Activer / Désactiver and Régénérer le mot de passe…, the new
 * challenge shown once in a dialog (M05), and what the product has more behind the page switch:
 * the requests (approve, reject with a reason), the Intune registrations, and the rights.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts === 'object' && Object.keys(opts).length ? `${key} ${JSON.stringify(opts)}` : key),
    i18n: { language: 'fr', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ i18nKey }) => i18nKey,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const notify = vi.hoisted(() => ({ showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn().mockResolvedValue(true) }))
const perms = vi.hoisted(() => ({ write: true }))
const clip = vi.hoisted(() => ({ copy: vi.fn().mockResolvedValue(false) }))
vi.mock('../../contexts', () => ({ useNotification: () => notify, useMobile: () => ({ isMobile: false }) }))
vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: persisted.usePersistedState,
    usePermission: () => ({ hasPermission: () => perms.write, canWrite: () => perms.write }),
    useClipboard: () => clip,
  }
})
vi.mock('../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))

const scep = vi.hoisted(() => ({
  getConfig: vi.fn(), getStats: vi.fn(), getProfiles: vi.fn(), getRequests: vi.fn(), getRequest: vi.fn(), getIntuneApps: vi.fn(),
  updateProfile: vi.fn(), regenerateProfileChallenge: vi.fn(), approveRequest: vi.fn(), rejectRequest: vi.fn(), deleteIntuneApp: vi.fn(),
  getChallenge: vi.fn(), deleteProfile: vi.fn(),
}))
vi.mock('../../services', () => ({
  scepService: scep,
  casService: { getAll: vi.fn().mockResolvedValue({ data: [{ id: 3, refid: 'ca-3', descr: 'IoT CA', has_private_key: true }] }) },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))

import SCEPPage from '../SCEPPage'

const PROFILES = [
  { id: 1, name: 'Équipements réseau', url_slug: 'reseau', ca_refid: 'ca-3', ca_name: 'IoT CA', template_name: 'Équipement réseau', challenge_set: true, auto_approve: false, enabled: true, intune_enabled: false },
  { id: 2, name: 'Postes nomades', url_slug: 'mdm', ca_refid: 'ca-3', ca_name: 'IoT CA', template_name: null, challenge_set: false, auto_approve: true, enabled: false, intune_enabled: true },
]
const REQUEST = { id: 9, subject: 'CN=device-9,O=Lab', transaction_id: 'tx-9', status: 'pending', created_at: '2026-11-08T10:00:00Z', ca_refid: 'ca-3', profile_id: 1 }

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  perms.write = true
  clip.copy.mockResolvedValue(false)
  scep.getConfig.mockResolvedValue({ data: { enabled: true } })
  scep.getStats.mockResolvedValue({ data: { pending: 1, approved: 2, rejected: 0, total: 3 } })
  scep.getProfiles.mockResolvedValue({ data: PROFILES })
  scep.getRequests.mockResolvedValue({ data: [REQUEST], meta: { total: 1 } })
  scep.getIntuneApps.mockResolvedValue({ data: [
    { id: 7, name: 'Corp Intune', tenant_id: 'corp.onmicrosoft.com', client_id: 'client-7', profile_count: 2, profile_names: ['Windows', 'iOS'] },
    { id: 8, name: 'Lab Intune', tenant_id: 'lab.onmicrosoft.com', client_id: 'client-8', profile_count: 0, profile_names: [] },
  ] })
  scep.updateProfile.mockResolvedValue({})
  scep.regenerateProfileChallenge.mockResolvedValue({ data: { challenge: 'NEW-SECRET-01' } })
  scep.approveRequest.mockResolvedValue({})
  scep.rejectRequest.mockResolvedValue({})
})

const at = (path) => render(<MemoryRouter initialEntries={[path]}><SCEPPage /></MemoryRouter>)
const dock = () => screen.findByRole('complementary', { name: /atelier.detailOf/ })

describe('the SCEP profiles', () => {
  it('draws the mockup list: chips with counters and the columns the product has', async () => {
    at('/scep-config')
    await screen.findByRole('button', { name: 'Équipements réseau' })
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent))
      .toEqual(['atelier.name', 'scep.columns.ca', 'scep.columns.template', 'Intune', 'atelier.state', 'common.actions'])
    const chips = within(screen.getByRole('group', { name: 'scep.filterByState' })).getAllByRole('button').map((b) => b.textContent)
    expect(chips).toEqual(['common.all2', 'scep.filters.active1', 'scep.filters.disabled1', 'Intune1'])
    // No OAEP column: a capability of the envelope, never a per-profile flag
    expect(screen.queryByText('OAEP')).toBeNull()
  })

  it('disables a profile from its dock and gives the focus back to the button', async () => {
    at('/scep-config')
    fireEvent.click(await screen.findByRole('button', { name: 'Équipements réseau' }))
    const d = await dock()
    fireEvent.click(within(d).getByRole('button', { name: 'scep.disable' }))
    await waitFor(() => expect(scep.updateProfile).toHaveBeenCalledWith(1, { enabled: false }))
    expect(await within(d).findByRole('button', { name: 'scep.enable' })).toBeInTheDocument()
  })

  it('asks before regenerating, then shows the new challenge once even when the clipboard fails (M05)', async () => {
    at('/scep-config')
    fireEvent.click(await screen.findByRole('button', { name: 'Équipements réseau' }))
    fireEvent.click(within(await dock()).getByRole('button', { name: 'scep.rotate' }))
    const ask = await screen.findByRole('dialog', { name: 'scep.rotateTitle' })
    expect(ask).toHaveTextContent('scep.rotateWarning')
    expect(scep.regenerateProfileChallenge).not.toHaveBeenCalled()
    fireEvent.click(within(ask).getByRole('button', { name: 'scep.regenerate' }))
    const shown = await screen.findByRole('dialog', { name: 'scep.newChallengeTitle' })
    expect(within(shown).getByText('NEW-SECRET-01')).toBeInTheDocument()
    fireEvent.click(within(shown).getByRole('button', { name: 'common.copy' }))
    await waitFor(() => expect(clip.copy).toHaveBeenCalledWith('NEW-SECRET-01'))
    fireEvent.click(within(shown).getByRole('button', { name: 'common.close' }))
    expect(screen.queryByText('NEW-SECRET-01')).toBeNull()
  })

  it('says copied only when the clipboard took the value, and keeps a failed rotation out of the dialog', async () => {
    at('/scep-config')
    fireEvent.click(await screen.findByRole('button', { name: 'Équipements réseau' }))
    fireEvent.click(within(await dock()).getByRole('button', { name: 'scep.rotate' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'scep.rotateTitle' })).getByRole('button', { name: 'scep.regenerate' }))
    const shown = await screen.findByRole('dialog', { name: 'scep.newChallengeTitle' })
    fireEvent.click(within(shown).getByRole('button', { name: 'common.copy' }))
    await waitFor(() => expect(clip.copy).toHaveBeenCalled())
    expect(notify.showSuccess).not.toHaveBeenCalledWith('common.copied')
    fireEvent.click(within(shown).getByRole('button', { name: 'common.close' }))
    // The server refuses: its reason, and no value to show
    scep.regenerateProfileChallenge.mockRejectedValue(new Error('CA offline'))
    fireEvent.click(within(await dock()).getByRole('button', { name: 'scep.rotate' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'scep.rotateTitle' })).getByRole('button', { name: 'scep.regenerate' }))
    await waitFor(() => expect(notify.showError).toHaveBeenCalledWith('CA offline'))
    expect(screen.queryByRole('dialog', { name: 'scep.newChallengeTitle' })).toBeNull()
  })

  it('rotates nothing when the dialog is cancelled, and deletes through the shared confirmation', async () => {
    const browserConfirm = vi.fn(() => true)
    vi.stubGlobal('confirm', browserConfirm)
    at('/scep-config')
    fireEvent.click(await screen.findByRole('button', { name: 'Équipements réseau' }))
    fireEvent.click(within(await dock()).getByRole('button', { name: 'scep.rotate' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'scep.rotateTitle' })).getByRole('button', { name: 'common.cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'scep.rotateTitle' })).toBeNull())
    expect(scep.regenerateProfileChallenge).not.toHaveBeenCalled()
    notify.showConfirm.mockResolvedValueOnce(false)
    fireEvent.click(within(await dock()).getByRole('button', { name: 'common.delete' }))
    await waitFor(() => expect(notify.showConfirm).toHaveBeenCalled())
    expect(scep.deleteProfile).not.toHaveBeenCalled()
    fireEvent.click(within(await dock()).getByRole('button', { name: 'common.delete' }))
    await waitFor(() => expect(scep.deleteProfile).toHaveBeenCalledWith(1))
    expect(browserConfirm).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('offers no rotation for an Intune profile and no action without write:scep', async () => {
    at('/scep-config')
    fireEvent.click(await screen.findByRole('button', { name: 'Postes nomades' }))
    expect(within(await dock()).queryByRole('button', { name: 'scep.rotate' })).toBeNull()
    perms.write = false
    fireEvent.click(screen.getByRole('button', { name: 'Équipements réseau' }))
    const d = await dock()
    expect(within(d).queryByRole('button', { name: 'scep.disable' })).toBeNull()
    expect(within(d).queryByRole('button', { name: 'scep.rotate' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'scep.newProfile' })).toBeNull()
  })
})

describe('the SCEP requests', () => {
  it('filters by state on the server and approves a pending request', async () => {
    at('/scep-config?tab=requests')
    fireEvent.click(await screen.findByRole('button', { name: 'device-9' }))
    fireEvent.click(within(screen.getByRole('group', { name: 'scep.filterByState' })).getByRole('button', { name: /common.pending/ }))
    await waitFor(() => expect(scep.getRequests.mock.calls.at(-1)[0]).toMatchObject({ status: ['pending'], page: 1 }))
    fireEvent.click(within(await dock()).getByRole('button', { name: 'scep.approve' }))
    await waitFor(() => expect(scep.approveRequest).toHaveBeenCalledWith(9))
  })

  it('rejects with the typed reason', async () => {
    at('/scep-config?tab=requests')
    fireEvent.click(await screen.findByRole('button', { name: 'device-9' }))
    fireEvent.click(within(await dock()).getByRole('button', { name: 'scep.reject' }))
    const d = await screen.findByRole('dialog', { name: 'scep.rejectRequest' })
    fireEvent.change(within(d).getByLabelText('scep.rejectionReason'), { target: { value: 'unknown device' } })
    fireEvent.click(within(d).getByRole('button', { name: 'scep.rejectRequest' }))
    await waitFor(() => expect(scep.rejectRequest).toHaveBeenCalledWith(9, 'unknown device'))
  })

  it('opens a linked request even past the page (?request=N)', async () => {
    scep.getRequest.mockResolvedValue({ data: { ...REQUEST, id: 77, subject: 'CN=far-away', transaction_id: 'tx-77' } })
    at('/scep-config?tab=requests&request=77')
    expect(await within(await dock()).findByText('tx-77')).toBeInTheDocument()
  })
})

describe('the Intune registrations', () => {
  it('lists the registrations with the profiles that use them', async () => {
    at('/scep-config?tab=intune')
    fireEvent.click(await screen.findByRole('button', { name: 'Corp Intune' }))
    expect(screen.getAllByRole('row')[1]).toHaveTextContent('scep.intuneAppUsedBy {"count":2}')
    expect(screen.getAllByRole('row')[2]).toHaveTextContent('scep.intuneAppNotUsed')
    expect(await dock()).toHaveTextContent('Windows, iOS')
  })

  it('shows the server reason when a registration in use cannot be deleted', async () => {
    scep.deleteIntuneApp.mockRejectedValue(new Error('Cannot delete: used by 2 SCEP profile(s): Windows, iOS'))
    at('/scep-config?tab=intune')
    fireEvent.click(await screen.findByRole('button', { name: 'Corp Intune' }))
    fireEvent.click(within(await dock()).getByRole('button', { name: 'common.delete' }))
    await waitFor(() => expect(scep.deleteIntuneApp).toHaveBeenCalledWith(7))
    expect(notify.showError).toHaveBeenCalledWith('Cannot delete: used by 2 SCEP profile(s): Windows, iOS')
    expect(notify.showConfirm).toHaveBeenCalledWith('scep.intuneAppDeleteConfirm {"name":"Corp Intune"}', expect.anything())
  })
})
