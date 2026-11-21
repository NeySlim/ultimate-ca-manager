/**
 * Copying is reported honestly, everywhere (DUP-FE-009).
 *
 * UCM is an on-prem PKI and is very often reached over plain HTTP, where
 * `navigator.clipboard` simply does not exist. Fourteen surfaces still copied
 * by hand, and on that transport each of them either threw a TypeError inside
 * a click handler or announced a success that never happened:
 *
 *  - the SMTP OAuth redirect URI used `navigator.clipboard?.writeText(val)` and
 *    then showed "Copied to clipboard" unconditionally — the `?.` short-circuits
 *    and the operator is told the URI is on the clipboard when it is not;
 *  - rotating a SCEP profile challenge called
 *    `navigator.clipboard.writeText(c).catch(...)`, which throws BEFORE `.catch`
 *    is attached: the outer catch then reported failure and skipped
 *    `onChanged()`, even though the server had already rotated the challenge
 *    (every enrolled device has stopped enrolling) and the new challenge is
 *    shown exactly once;
 *  - the PEM / field copy buttons flipped to "Copied!" without awaiting or
 *    catching anything.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}))
const scepMocks = vi.hoisted(() => ({
  regenerateProfileChallenge: vi.fn(),
  deleteProfile: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn() }),
  useAuth: () => ({ user: { role: 'admin' }, permissions: ['*'], isAuthenticated: true }),
  useInspector: () => ({ windows: [], openEntity: vi.fn(), closeWindow: vi.fn() }),
}))

vi.mock('../../services', () => ({
  scepService: scepMocks,
}))

import { CompactField, DetailField } from '../DetailCard'
import { CSRPanel } from '../detail/CSRPanel'
import { TrustCertPanel } from '../detail/TrustCertPanel'
import CopyableUrl from '../../pages/settings/CopyableUrl'
import EmailSection from '../../pages/settings/EmailSection'
import ScepProfilesTab from '../../pages/scep/ScepProfilesTab'

// ── transports ──────────────────────────────────────────────────────────────
// Two ways a copy fails in the field, and the one way it works.

const realExecCommand = document.execCommand

function setSecureContext(value) {
  Object.defineProperty(window, 'isSecureContext', {
    value, configurable: true, writable: true,
  })
}

function setClipboard(value) {
  Object.defineProperty(navigator, 'clipboard', {
    value, configurable: true, writable: true,
  })
}

/** Plain HTTP: no navigator.clipboard at all, and no execCommand fallback. */
function plainHttp() {
  setSecureContext(false)
  setClipboard(undefined)
  document.execCommand = vi.fn(() => false)
}

/** HTTPS, but the browser or a policy refuses the write. */
function refusedWrite() {
  const writeText = vi.fn(() => Promise.reject(new DOMException('denied')))
  setSecureContext(true)
  setClipboard({ writeText })
  return writeText
}

/** HTTPS and everything works. */
function workingClipboard() {
  const writeText = vi.fn(() => Promise.resolve())
  setSecureContext(true)
  setClipboard({ writeText })
  return writeText
}

beforeEach(() => {
  Object.values(notify).forEach(fn => fn.mockReset())
  Object.values(scepMocks).forEach(fn => fn.mockReset())
  scepMocks.regenerateProfileChallenge.mockResolvedValue({ data: { challenge: 'new-secret' } })
  plainHttp()
})

afterEach(() => {
  document.execCommand = realExecCommand
  setClipboard(undefined)
})

// ── 1. the SMTP OAuth redirect URI ──────────────────────────────────────────

const EMAIL_PROPS = {
  settings: {
    smtp_auth_method: 'oauth2',
    smtp_oauth_provider: 'google',
    smtp_oauth_redirect_uri: 'https://pki.example.com/api/v2/settings/email/oauth/callback',
  },
  updateSetting: vi.fn(),
  handleSave: vi.fn(),
  saving: false,
  canWrite: () => true,
  isMobile: false,
  emailTestResult: null,
  emailTesting: false,
  handleTestEmail: vi.fn(),
  oauthDirty: false,
  setOauthDirty: vi.fn(),
  oauthPresets: {},
  applyOAuthProviderPreset: vi.fn(),
  handleSmtpOAuthAuthorize: vi.fn(),
  handleSmtpOAuthRevoke: vi.fn(),
  expiryAlerts: {},
  setExpiryAlerts: vi.fn(),
  saveExpiryAlerts: vi.fn(),
  triggerExpiryCheck: vi.fn(),
  showTemplateEditor: false,
  setShowTemplateEditor: vi.fn(),
}

const clickCopy = () => {
  const button = screen.getAllByText('common.copy')
    .map(node => node.closest('button'))
    .find(Boolean)
  fireEvent.click(button)
}

describe('SMTP OAuth redirect URI', () => {
  it('does not claim the URI was copied when there is no clipboard', async () => {
    render(<EmailSection {...EMAIL_PROPS} />)
    clickCopy()

    await waitFor(() => expect(document.execCommand).toHaveBeenCalled())
    expect(notify.showSuccess).not.toHaveBeenCalled()
  })

  it('does not claim it either when the browser refuses the write', async () => {
    const writeText = refusedWrite()
    render(<EmailSection {...EMAIL_PROPS} />)
    clickCopy()

    await waitFor(() => expect(writeText).toHaveBeenCalled())
    await waitFor(() => expect(notify.showSuccess).not.toHaveBeenCalled())
  })

  it('still confirms the copy when it works', async () => {
    const writeText = workingClipboard()
    render(<EmailSection {...EMAIL_PROPS} />)
    clickCopy()

    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalledWith('common.copiedToClipboard'))
    expect(writeText).toHaveBeenCalledWith(EMAIL_PROPS.settings.smtp_oauth_redirect_uri)
  })
})

// ── 2. SCEP profile challenge rotation ──────────────────────────────────────

const PROFILE = { id: 3, name: 'Kiosks', url_slug: 'kiosks', ca_refid: 'ca-1', enabled: true }

const renderProfiles = (onChanged) => render(
  <ScepProfilesTab profiles={[PROFILE]} cas={[]} templates={[]} canWrite onChanged={onChanged} />
)

describe('SCEP profile challenge rotation', () => {
  it('refreshes the table even when the challenge cannot be copied', async () => {
    notify.showConfirm.mockResolvedValue(true)
    const onChanged = vi.fn()
    renderProfiles(onChanged)
    fireEvent.click(screen.getByLabelText('scep.regenerate'))

    await waitFor(() => expect(scepMocks.regenerateProfileChallenge).toHaveBeenCalledWith(PROFILE.id))
    // The rotation succeeded; the clipboard is a courtesy, not a gate.
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    expect(notify.showError).not.toHaveBeenCalled()
  })

  it('does not say "copied to clipboard" when nothing was copied', async () => {
    notify.showConfirm.mockResolvedValue(true)
    renderProfiles(vi.fn())
    fireEvent.click(screen.getByLabelText('scep.regenerate'))

    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalled())
    // scep.profileChallengeRegenerated reads "…and copied to clipboard".
    expect(notify.showSuccess).not.toHaveBeenCalledWith('scep.profileChallengeRegenerated')
    expect(notify.showSuccess).toHaveBeenCalledWith('scep.challengeRegenerated')
  })

  it('keeps the full message when the challenge really did reach the clipboard', async () => {
    workingClipboard()
    notify.showConfirm.mockResolvedValue(true)
    const onChanged = vi.fn()
    renderProfiles(onChanged)
    fireEvent.click(screen.getByLabelText('scep.regenerate'))

    await waitFor(() => expect(notify.showSuccess).toHaveBeenCalledWith('scep.profileChallengeRegenerated'))
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  it('still surfaces a real server failure', async () => {
    notify.showConfirm.mockResolvedValue(true)
    scepMocks.regenerateProfileChallenge.mockRejectedValue(new Error('CA offline'))
    const onChanged = vi.fn()
    renderProfiles(onChanged)
    fireEvent.click(screen.getByLabelText('scep.regenerate'))

    await waitFor(() => expect(notify.showError).toHaveBeenCalledWith('CA offline'))
    expect(onChanged).not.toHaveBeenCalled()
  })
})

// ── 3. the "Copied!" badges ─────────────────────────────────────────────────

describe('DetailField copy badge', () => {
  it('does not flip to Copied! when the click cannot copy', async () => {
    render(<DetailField label="Serial" value="0A:0B:0C" copyable />)
    const target = screen.getByTitle('common.clickToCopy')
    fireEvent.click(target)

    await waitFor(() => expect(document.execCommand).toHaveBeenCalled())
    expect(screen.queryByTitle('common.copied')).toBeNull()
  })

  it('does not flip to Copied! when the write is refused', async () => {
    const writeText = refusedWrite()
    render(<DetailField label="Serial" value="0A:0B:0C" copyable />)
    fireEvent.click(screen.getByTitle('common.clickToCopy'))

    await waitFor(() => expect(writeText).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByTitle('common.copied')).toBeNull())
  })

  it('flips to Copied! once the value is really on the clipboard', async () => {
    const writeText = workingClipboard()
    render(<DetailField label="Serial" value="0A:0B:0C" copyable />)
    fireEvent.click(screen.getByTitle('common.clickToCopy'))

    await waitFor(() => expect(screen.getByTitle('common.copied')).toBeTruthy())
    expect(writeText).toHaveBeenCalledWith('0A:0B:0C')
  })
})

describe('CompactField copy button', () => {
  const renderField = () => render(
    <CompactField label="Fingerprint" value="AA:BB" autoIcon="fingerprint" copyable />
  )

  it('survives a click on plain HTTP without throwing', async () => {
    renderField()
    fireEvent.click(screen.getByTitle('Copy'))
    await waitFor(() => expect(document.execCommand).toHaveBeenCalled())
  })

  it('copies the value when the clipboard is available', async () => {
    const writeText = workingClipboard()
    renderField()
    fireEvent.click(screen.getByTitle('Copy'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('AA:BB'))
  })
})

describe('CopyableUrl', () => {
  it('stays quiet when the URL could not be copied', async () => {
    render(<CopyableUrl label="SCEP URL" value="http://pki.example.com/scep" />)
    fireEvent.click(screen.getByLabelText('common.copy'))

    await waitFor(() => expect(document.execCommand).toHaveBeenCalled())
    expect(notify.showInfo).not.toHaveBeenCalled()
  })

  it('confirms when it worked', async () => {
    workingClipboard()
    render(<CopyableUrl label="SCEP URL" value="http://pki.example.com/scep" />)
    fireEvent.click(screen.getByLabelText('common.copy'))

    await waitFor(() => expect(notify.showInfo).toHaveBeenCalledWith('common.copiedToClipboard'))
  })
})

const PEM = '-----BEGIN CERTIFICATE REQUEST-----\nMIIB\n-----END CERTIFICATE REQUEST-----'

describe('PEM copy buttons', () => {
  it('CSRPanel does not claim the PEM was copied on plain HTTP', async () => {
    render(<CSRPanel csr={{ id: 1, subject: 'CN=web', pem: PEM }} />)
    fireEvent.click(screen.getByText('details.copyPem'))

    await waitFor(() => expect(document.execCommand).toHaveBeenCalled())
    expect(screen.queryByText('common.copied')).toBeNull()
  })

  it('CSRPanel confirms a copy that worked', async () => {
    const writeText = workingClipboard()
    render(<CSRPanel csr={{ id: 1, subject: 'CN=web', pem: PEM }} />)
    fireEvent.click(screen.getByText('details.copyPem'))

    await waitFor(() => expect(screen.getByText('common.copied')).toBeTruthy())
    expect(writeText).toHaveBeenCalledWith(PEM)
  })

  it('TrustCertPanel does not claim it either', async () => {
    render(<TrustCertPanel cert={{ id: 1, subject: 'CN=root', pem: PEM }} />)
    fireEvent.click(screen.getByText('details.copyPem'))

    await waitFor(() => expect(document.execCommand).toHaveBeenCalled())
    expect(screen.queryByText('common.copied')).toBeNull()
  })

  it('TrustCertPanel confirms a copy that worked', async () => {
    workingClipboard()
    render(<TrustCertPanel cert={{ id: 1, subject: 'CN=root', pem: PEM }} />)
    fireEvent.click(screen.getByText('details.copyPem'))

    await waitFor(() => expect(screen.getByText('common.copied')).toBeTruthy())
  })
})

// ── 4. nobody re-implements the copy path ───────────────────────────────────
// The surfaces below are pages too large to drive here; reading the source is
// enough to catch one of them going back to its own navigator.clipboard call
// and its own uncleaned setTimeout.

const SRC = join(__dirname, '..', '..')
const read = (rel) => readFileSync(join(SRC, rel), 'utf8')

const MIGRATED = [
  'hooks/useClipboard.js',
  'pages/settings/EmailSection.jsx',
  'pages/settings/CopyableUrl.jsx',
  'pages/settings/DeploySection.jsx',
  'pages/scep/ScepProfilesTab.jsx',
  'pages/ESTPage.jsx',
  'pages/TSAPage.jsx',
  'pages/SCEPPage.jsx',
  'components/DetailCard.jsx',
  'components/detail/CSRPanel.jsx',
  'components/detail/CAPanel.jsx',
  'components/detail/CertificatePanel.jsx',
  'components/detail/TrustCertPanel.jsx',
]

describe('the copy path is not re-implemented', () => {
  it.each(MIGRATED.filter(f => f !== 'hooks/useClipboard.js'))(
    '%s goes through useClipboard instead of navigator.clipboard',
    (file) => {
      const source = read(file)
      expect(source).not.toMatch(/navigator\s*\.\s*clipboard/)
      expect(source).toMatch(/useClipboard/)
    },
  )

  it.each(['components/detail/CSRPanel.jsx', 'components/detail/CAPanel.jsx',
    'components/detail/CertificatePanel.jsx', 'components/detail/TrustCertPanel.jsx',
    'components/DetailCard.jsx', 'pages/settings/DeploySection.jsx'])(
    '%s no longer owns an uncleaned copy-reset timer',
    (file) => {
      expect(read(file)).not.toMatch(/setTimeout\(\s*\(\)\s*=>\s*set\w*Copied\(false\)/)
    },
  )
})
