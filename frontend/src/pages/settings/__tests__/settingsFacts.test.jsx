/**
 * Settings read as typed facts (KV-3, zone E): a digest or a path in a copy chip that copies the whole value,
 * a state as a pill, an absent value muted apart from the values, a DN or a sentence on a long row,
 * and no button left in the value column.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

const { notify, db, msca } = vi.hoisted(() => ({
  notify: { showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn() },
  db: { getStatus: vi.fn(), testConnection: vi.fn() },
  msca: { caHealth: vi.fn(), caPending: vi.fn() },
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'en' } }),
}))
vi.mock('../../../contexts', () => ({ useNotification: () => notify }))
vi.mock('../../../contexts/NotificationContext', () => ({ useNotification: () => notify }))
vi.mock('../../../services', () => ({ databaseService: db, mscaService: msca }))

import HttpsSection from '../HttpsSection'
import DatabaseSection from '../DatabaseSection'
import DatabaseBackendSection from '../DatabaseBackendSection'
import SecuritySection from '../SecuritySection'
import SignInTestReport from '../sso/SignInTestReport'
import MappingTestResult from '../sso/MappingTestResult'
import { UpdateCampaignStatus } from '../../../components/UpdateCampaignStatus'
import { MscaCaControlModal } from '../../../components/MscaCaControlModal'
import { Facts } from '../../../components/atelier'
import { fact } from '../../../components/atelier/facts'

const FP = 'AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89'
const URI = 'postgresql://ucm:***@db.example.com:5432/ucm_production_database'
let writeText

beforeEach(() => {
  Object.values(notify).forEach((f) => f.mockReset())
  writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
})

// The row of a term, and the value column holds no button but a copy chip's own
const row = (term) => [...document.querySelectorAll('dl.kv > div.row')].find((r) => r.querySelector('dt')?.textContent === term)
const loneButtons = () => [...document.querySelectorAll('dl.kv dd.v button')].filter((b) => !b.closest('.code-value'))

describe('a fact of the settings', () => {
  it('keeps a missing long value short and beside its term, and a zero as a value', () => {
    render(<Facts items={[fact('Note', null, { long: true }), fact('Runs', 0), fact('Path', '/var/x', { kind: 'url', long: true })]} />)
    expect(row('Note')).not.toHaveClass('long')
    expect(row('Note').querySelector('dd')).toHaveClass('absent')
    expect(row('Runs').querySelector('dd.v')).toHaveTextContent('0')
    expect(row('Path')).toHaveClass('long')
    expect(row('Path').querySelector('.code-value.url')).not.toBeNull()
  })
})

describe('the HTTPS certificate', () => {
  const show = (info) => render(<HttpsSection httpsInfo={info} selectedHttpsCert={null} setSelectedHttpsCert={vi.fn()} setShowCertPicker={vi.fn()}
    handleApplyUcmCert={vi.fn()} handleRegenerateHttpsCert={vi.fn()} setShowHttpsImportModal={vi.fn()} />)

  it('copies its whole fingerprint from a digest chip, and says an absent issuer apart', async () => {
    show({ common_name: 'ucm.example.com', fingerprint: FP, valid_from: '2026-01-01T00:00:00Z', valid_to: '2027-01-01T00:00:00Z' })
    expect(document.querySelector('dl.props')).toBeNull()
    const fp = row('settings.fingerprintSha256')
    expect(fp.querySelector('dd.v .code-value.hex')).not.toBeNull()
    fireEvent.click(within(fp).getByRole('button', { name: /protocols\.copyValue/ }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(FP))
    const issuer = row('common.issuer').querySelector('dd')
    expect(issuer).toHaveClass('absent')
    expect(issuer).toHaveTextContent('—')
  })

  it('offers no copy of a fingerprint the API could not read', () => {
    show({ common_name: 'Error reading certificate', issuer: 'Unknown', fingerprint: '-' })
    expect(row('settings.fingerprintSha256').querySelector('dd')).toHaveClass('absent')
    expect(document.querySelector('.code-value')).toBeNull()
    expect(row('common.issuer').querySelector('dd.v')).toHaveTextContent('Unknown')
  })
})

describe('the database', () => {
  it('says the statistics it does not have apart from the values', () => {
    render(<DatabaseSection dbStats={{ certificates: 12 }} handleOptimizeDb={vi.fn()} handleIntegrityCheck={vi.fn()} handleExportDb={vi.fn()} handleResetDb={vi.fn()} />)
    expect(row('settings.totalCertificates').querySelector('dd')).toHaveClass('v')
    expect(row('settings.lastOptimized').querySelector('dd')).toHaveClass('absent')
  })

  it('reads its URI in a URL chip that copies it whole, and its health as a state', async () => {
    db.getStatus.mockResolvedValue({ data: { backend: 'postgresql', version: '16.4', table_count: 80, size_bytes: 1024, uri_redacted: URI, healthy: true } })
    render(<DatabaseBackendSection />)
    await screen.findByText('settings.backend.uri')
    const uri = row('settings.backend.uri')
    expect(uri.querySelector('dd.v .code-value.url')).not.toBeNull()
    fireEvent.click(within(uri).getByRole('button', { name: /protocols\.copyValue/ }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(URI))
    expect(row('settings.backend.health').querySelector('dd.v .badge.good')).toHaveTextContent('settings.backend.healthy')
    expect(loneButtons()).toEqual([])
  })
})

describe('the key encryption', () => {
  const show = (enc) => render(<SecuritySection settings={{}} updateSetting={vi.fn()} hasPermission={() => false} encryptionStatus={enc}
    setShowEnableEncryptionModal={vi.fn()} setShowDisableEncryptionModal={vi.fn()} anomalies={[]} anomaliesLoading={false} loadAnomalies={vi.fn()}
    mtlsSettings={{}} setMtlsSettings={vi.fn()} mtlsLoading={false} cas={[]} />)

  it('reads its state as a pill, its key file as a path to copy and its master key fingerprint as a digest', async () => {
    show({ enabled: true, key_source: 'file', key_file_path: '/etc/ucm/master.key', kek_fingerprint: 'd40223ab994955cb', dek_version: 1, total_keys: 0, key_files_on_disk: 0 })
    expect(row('common.status').querySelector('dd.v .badge.good')).toHaveTextContent('common.enabled')
    const path = row('settings.keySource')
    expect(path.querySelector('dd.v .code-value.url')).not.toBeNull()
    fireEvent.click(within(path).getByRole('button', { name: /protocols\.copyValue/ }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('/etc/ucm/master.key'))
    expect(row('settings.kekFingerprint').querySelector('dd.v .code-value.hex')).not.toBeNull()
  })

  it('says a key source without a file apart from the values', () => {
    show({ enabled: true, key_source: 'env', key_file_path: null, total_keys: 0, key_files_on_disk: 0 })
    expect(row('settings.keySource').querySelector('dd')).toHaveClass('absent')
  })
})

describe('the SSO tests', () => {
  it('gives the sign-in verdict as a state with the login message under it, and the reason on a long row', () => {
    render(<SignInTestReport report={{ verdict: 'refused', code: 'sso_unmapped', reason: 'No group of the identity maps to a role of UCM.' }} formData={{}} />)
    const verdict = row('sso.signInTestVerdict')
    expect(verdict.querySelector('dd.v .badge.bad')).toHaveTextContent('sso.signInTestRefused')
    expect(verdict.querySelector('dd.v > .sub')).toHaveTextContent('auth.ssoUnmapped')
    expect(row('sso.signInTestReason')).toHaveClass('long')
  })

  it('puts the DN of the LDAP mapping test on a long row and its access as a state', () => {
    render(<MappingTestResult result={{ found: true, user_dn: 'CN=Alice Martin,OU=Users,DC=lab,DC=example,DC=com', groups: [], access_allowed: true, resolved_role: 'viewer' }} />)
    expect(row('DN')).toHaveClass('long')
    expect(row('sso.testMappingAccess').querySelector('dd.v .badge.good')).toHaveTextContent('sso.testMappingAccessAllowed')
  })
})

describe('the HA update campaign', () => {
  it('says a node not yet at work apart from the values', () => {
    render(<UpdateCampaignStatus campaign={{ target: '3.1', status: 'running', order: ['a', 'b'], done: ['a'] }} />)
    expect(row('settings.updateCampaign.nodesDone').querySelector('dd')).toHaveClass('v')
    const current = row('settings.updateCampaign.currentNode').querySelector('dd')
    expect(current).toHaveClass('absent')
    expect(current).toHaveTextContent('settings.updateCampaign.none')
  })
})

describe('the Microsoft CA control', () => {
  it('reads the service of the remote CA as a state', async () => {
    msca.caHealth.mockResolvedValue({ data: { certsvc_status: 'Stopped', pending_count: 0 } })
    msca.caPending.mockResolvedValue({ data: [] })
    render(<MscaCaControlModal open connection={{ id: 3, name: 'corp' }} onClose={vi.fn()} />)
    await waitFor(() => expect(row('msca.healthService').querySelector('dd.v .badge.bad')).toHaveTextContent('Stopped'))
    expect(row('msca.healthCrl').querySelector('dd')).toHaveClass('absent')
    expect(screen.getAllByText('msca.healthPending')).toHaveLength(1)
  })
})
