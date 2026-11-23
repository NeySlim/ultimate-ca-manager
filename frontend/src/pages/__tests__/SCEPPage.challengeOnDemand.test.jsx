/**
 * The challenges of the CAs: the list and the dock show each state from one listing, without the secret; the secret is
 * read only when asked, one read per Show or Copy, never when the view or a dock opens.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() } }),
  Trans: ({ i18nKey }) => i18nKey,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
const notify = vi.hoisted(() => ({ showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn() }))
const clip = vi.hoisted(() => ({ copy: vi.fn() }))
const perm = vi.hoisted(() => ({ write: true }))
vi.mock('../../contexts', () => ({ useNotification: () => notify, useMobile: () => ({ isMobile: false }) }))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
vi.mock('../../hooks', async () => ({
  usePersistedState: (await vi.importActual('../../hooks/usePersistedState')).usePersistedState,
  usePermission: () => ({ hasPermission: () => perm.write, canWrite: () => perm.write }),
  useClipboard: () => clip,
}))
vi.mock('../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))
const scep = vi.hoisted(() => ({
  getConfig: vi.fn(), getStats: vi.fn(), getProfiles: vi.fn(), getRequests: vi.fn(), getRequest: vi.fn(), getIntuneApps: vi.fn(),
  getChallenge: vi.fn(), getChallengeStates: vi.fn(), regenerateChallenge: vi.fn(),
}))
vi.mock('../../services', () => ({
  scepService: scep,
  casService: { getAll: vi.fn().mockResolvedValue({ data: [
    { id: 3, refid: 'ca-3', name: 'IoT CA', subject: 'CN=IoT CA' },
    { id: 4, refid: 'ca-4', name: 'Branch CA', subject: 'CN=Branch CA' },
    { id: 5, refid: 'ca-5', name: 'Old CA', subject: 'CN=Old CA' },
  ] }) },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))
vi.mock('../../components/shell/useSetup', async (actual) => ({ ...(await actual()), useSetup: () => ({ visible: false }) }))

import { renderAtUrl } from '../../test/dockUrl'
import SCEPPage from '../SCEPPage'

const hoursAgo = (h) => new Date(Date.now() - h * 3600000).toISOString()

beforeEach(() => {
  vi.clearAllMocks()
  perm.write = true
  clip.copy.mockResolvedValue(true)
  scep.getConfig.mockResolvedValue({ data: { enabled: true } })
  scep.getStats.mockResolvedValue({ data: {} })
  scep.getProfiles.mockResolvedValue({ data: [] })
  scep.getRequests.mockResolvedValue({ data: [], meta: { total: 0 } })
  scep.getIntuneApps.mockResolvedValue({ data: [] })
  scep.getChallengeStates.mockResolvedValue({ data: [
    { ca_id: 3, configured: true, expired: false, generated_at: hoursAgo(2), expires_at: hoursAgo(-22) },
    { ca_id: 4, configured: false, expired: false, generated_at: null, expires_at: null },
    { ca_id: 5, configured: true, expired: true, generated_at: hoursAgo(30), expires_at: hoursAgo(6) },
  ] })
  scep.getChallenge.mockResolvedValue({ data: { challenge: 'S3CRET-VALUE' } })
})

const rowOf = (container, name) => within(container).getByRole('button', { name }).closest('tr')

describe('the challenges of the CAs', () => {
  it('opening the view lists every state at once and reads no secret', async () => {
    const at = renderAtUrl(<SCEPPage />, '/scep-config?tab=challenges')
    await screen.findByRole('button', { name: 'Old CA' })
    expect(scep.getChallengeStates).toHaveBeenCalledTimes(1)
    expect(scep.getChallenge).not.toHaveBeenCalled()
    expect(rowOf(at.container, 'IoT CA')).toHaveTextContent('scep.challengeSet')
    expect(rowOf(at.container, 'Branch CA')).toHaveTextContent('scep.noChallengeSet')
    expect(rowOf(at.container, 'Old CA').querySelector('.badge.bad')).toHaveTextContent('scep.challengeExpired')
    expect(at.container).not.toHaveTextContent('S3CRET-VALUE')
  })

  it('searches the authorities of the list by name, and puts them back from the no-match block', async () => {
    const at = renderAtUrl(<SCEPPage />, '/scep-config?tab=challenges')
    await screen.findByRole('button', { name: 'Old CA' })
    fireEvent.change(screen.getByRole('searchbox', { name: 'scep.searchChallenges' }), { target: { value: 'iot' } })
    expect(screen.getByRole('button', { name: 'IoT CA' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Old CA' })).toBeNull()
    fireEvent.change(screen.getByRole('searchbox', { name: 'scep.searchChallenges' }), { target: { value: 'nothing-like-it' } })
    fireEvent.click(await screen.findByRole('button', { name: 'table.clearFilters' }))
    expect(await screen.findByRole('button', { name: 'Old CA' })).toBeInTheDocument()
    expect(at.container).not.toHaveTextContent('S3CRET-VALUE')
  })

  it('a dock shows the state masked; Show reads the secret once, Hide masks it again', async () => {
    renderAtUrl(<SCEPPage />, '/scep-config?tab=challenges&item=3')
    const show = await screen.findByRole('button', { name: 'scep.challengeShow' })
    expect(scep.getChallenge).not.toHaveBeenCalled()
    expect(document.body).not.toHaveTextContent('S3CRET-VALUE')
    fireEvent.click(show)
    expect(await screen.findByText('S3CRET-VALUE')).toBeInTheDocument()
    expect(scep.getChallenge).toHaveBeenCalledTimes(1)
    expect(scep.getChallenge).toHaveBeenCalledWith(3)
    fireEvent.click(screen.getByRole('button', { name: 'scep.challengeHide' }))
    expect(screen.queryByText('S3CRET-VALUE')).toBeNull()
    expect(scep.getChallenge).toHaveBeenCalledTimes(1)
  })

  it('Copy reads the secret once and copies it without showing it', async () => {
    renderAtUrl(<SCEPPage />, '/scep-config?tab=challenges&item=3')
    fireEvent.click(await screen.findByRole('button', { name: 'scep.challengeCopy' }))
    await waitFor(() => expect(clip.copy).toHaveBeenCalledWith('S3CRET-VALUE'))
    expect(scep.getChallenge).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('S3CRET-VALUE')).toBeNull()
  })

  it('a CA without a challenge, or a reader without the write right, has nothing to read', async () => {
    renderAtUrl(<SCEPPage />, '/scep-config?tab=challenges&item=4')
    await screen.findAllByText('scep.noChallengeSet')
    expect(screen.queryByRole('button', { name: 'scep.challengeShow' })).toBeNull()
    perm.write = false
    renderAtUrl(<SCEPPage />, '/scep-config?tab=challenges&item=3')
    await screen.findAllByRole('button', { name: 'IoT CA' })
    expect(screen.queryByRole('button', { name: 'scep.challengeShow' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'scep.challengeCopy' })).toBeNull()
  })
})
