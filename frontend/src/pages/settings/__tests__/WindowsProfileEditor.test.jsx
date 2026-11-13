/**
 * The profile editor: the realm as the KDC writes it, the keytab entries by realm, the checklist
 * of what a profile still lacks, and the warning when the connector serves another domain.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Stable references: the editor reloads whenever `t` or the notifier changes identity.
const mocks = vi.hoisted(() => ({
  t: (key, opts) => {
    if (!opts) return key
    return `${key}|${Object.entries(opts).map(([k, v]) => `${k}=${v}`).join('|')}`
  },
  notify: { showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn() },
  get: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  uploadKeytab: vi.fn(),
  getSettings: vi.fn(),
  connectors: vi.fn(),
  templates: vi.fn(),
  picked: { file: null },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mocks.t,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => mocks.notify,
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))
vi.mock('../../../services', () => ({
  windowsProfilesService: {
    get: mocks.get, create: mocks.create, update: mocks.update, uploadKeytab: mocks.uploadKeytab,
    getSettings: mocks.getSettings,
  },
  adConnectorsService: { list: mocks.connectors },
  templatesService: { getAll: mocks.templates },
}))
// A native select exposes the options and the helper text that the real one hides in a portal.
vi.mock('../../../components', async (orig) => {
  // The real Input and Textarea wrap a plain control; the label and the error are all that matter here
  const field = (Tag) => ({ label, error, helperText: _h, hasExistingValue: _e, ...props }) => (
    <>
      <Tag aria-label={label} {...props} />
      {error && <p>{error}</p>}
    </>
  )
  return {
  ...(await orig()),
  Input: field('input'),
  Textarea: field('textarea'),
  Select: ({ label, options = [], value, onChange, helperText }) => (
    <div data-testid={`field-${label}`}>
      <select aria-label={label} value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
        <option value="">-</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {helperText && <p>{helperText}</p>}
    </div>
  ),
  }
})
vi.mock('../../../components/FileUpload', () => ({
  FileUpload: ({ onFileSelect }) => (
    <button type="button" onClick={() => onFileSelect(mocks.picked.file)}>pick-keytab</button>
  ),
}))

import WindowsProfileEditor from '../WindowsProfileEditor'

const CAS = [
  { id: 1, refid: 'ca-1', descr: 'Signing CA', has_private_key: true },
  { id: 2, refid: 'ca-2', descr: 'Keyless root', certificate_only: true, has_private_key: false },
  { id: 3, refid: 'ca-3', descr: 'Offline CA', has_private_key: true, offline: true },
]

const PROFILE = {
  id: 7, name: 'corp', realm: 'CORP.EXAMPLE', is_default: false, enabled: true, connector_id: null,
  issuing_ca_refid: 'ca-1', policy_ca_refid: null, validity_days: 365, template_ids: [],
  keytab_set: true, keytab_entries: [], xcep_username: '', wstep_username: '',
}

const renderEditor = (profile = { id: 7, name: 'corp' }, props = {}) => render(
  <MemoryRouter>
    <WindowsProfileEditor profile={profile} cas={CAS} canWrite canUploadKeytab onSaved={vi.fn()} onCancel={vi.fn()} {...props} />
  </MemoryRouter>)

beforeEach(() => {
  for (const m of [mocks.get, mocks.create, mocks.update, mocks.uploadKeytab, mocks.getSettings,
    mocks.connectors, mocks.templates]) m.mockReset()
  Object.values(mocks.notify).forEach(m => m.mockReset())
  mocks.get.mockResolvedValue({ data: PROFILE })
  mocks.getSettings.mockResolvedValue({ data: { default_profile: { id: 1, name: 'default' } } })
  mocks.connectors.mockResolvedValue({ data: [] })
  mocks.templates.mockResolvedValue({ data: [{ id: 1, name: 'Workstation', autoenroll_enabled: true, is_active: true }] })
  mocks.create.mockResolvedValue({ data: { id: 9 } })
  mocks.update.mockResolvedValue({ data: PROFILE })
  mocks.picked.file = new File(['x'], 'k.keytab')
})

const realmInput = () => screen.getByLabelText('xcepWstep.realm')
const loaded = () => screen.findByText('Workstation')

describe('realm', () => {
  it('refuses a lowercase realm and says why, without calling the server', async () => {
    renderEditor(null)
    await loaded()
    fireEvent.change(screen.getByLabelText('xcepWstep.profileName'), { target: { value: 'lower' } })
    fireEvent.change(realmInput(), { target: { value: 'corp.example' } })
    fireEvent.click(screen.getByText('common.save'))
    await waitFor(() => expect(mocks.notify.showError).toHaveBeenCalledWith('xcepWstep.realmCapitals'))
    expect(screen.getByText('xcepWstep.realmCapitals')).toBeInTheDocument()
    expect(mocks.create).not.toHaveBeenCalled()
  })

  it('saves a realm in capitals as typed', async () => {
    renderEditor(null)
    await loaded()
    fireEvent.change(screen.getByLabelText('xcepWstep.profileName'), { target: { value: 'corp' } })
    fireEvent.change(realmInput(), { target: { value: 'CORP.EXAMPLE' } })
    fireEvent.click(screen.getByText('common.save'))
    await waitFor(() => expect(mocks.create).toHaveBeenCalled())
    expect(mocks.create.mock.calls[0][0]).toMatchObject({ name: 'corp', realm: 'CORP.EXAMPLE' })
  })
})

describe('keytab', () => {
  it('lists the stored entries by realm and flags a realm that is not the profile\'s', async () => {
    mocks.get.mockResolvedValue({ data: { ...PROFILE, keytab_entries: [
      { principal: 'HTTP/ucm.example@CORP.EXAMPLE', realm: 'CORP.EXAMPLE', kvno: 2, enctype: 18 },
      { principal: 'HTTP/ucm.example@OTHER.EXAMPLE', realm: 'OTHER.EXAMPLE', kvno: 2, enctype: 18 },
    ] } })
    renderEditor()
    const entries = await screen.findByTestId('keytab-entries')
    expect(within(entries).getByText('CORP.EXAMPLE')).toBeInTheDocument()
    expect(within(entries).getByText('OTHER.EXAMPLE')).toBeInTheDocument()
    expect(within(entries).getByText('HTTP/ucm.example@OTHER.EXAMPLE (kvno 2, etype 18)')).toBeInTheDocument()
    expect(within(entries).getByText('xcepWstep.keytabRealmDiffers|realm=CORP.EXAMPLE')).toBeInTheDocument()
    expect(within(entries).getAllByText('xcepWstep.keytabRealmMatches')).toHaveLength(1)
  })

  it('shows the entries of a chosen file by realm before anything is stored', async () => {
    mocks.uploadKeytab.mockResolvedValue({ data: {
      keytab_entries: [
        { principal: 'HTTP/ucm.example@OTHER.EXAMPLE', realm: 'OTHER.EXAMPLE', kvno: 3, enctype: 18 },
      ],
      realms: ['OTHER.EXAMPLE'], profile_realm: 'CORP.EXAMPLE',
      foreign_entries: ['HTTP/ucm.example@OTHER.EXAMPLE'],
    } })
    renderEditor()
    await screen.findByText('pick-keytab')
    fireEvent.click(screen.getByText('pick-keytab'))
    await waitFor(() => expect(mocks.uploadKeytab).toHaveBeenCalledWith(7, mocks.picked.file, { dryRun: true }))
    expect(await screen.findByText('xcepWstep.keytabPreview')).toBeInTheDocument()
    expect(screen.getByText('OTHER.EXAMPLE')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('HTTP/ucm.example@OTHER.EXAMPLE')
  })

  it('stores the file with the profile on Save', async () => {
    mocks.uploadKeytab.mockResolvedValue({ data: { keytab_entries: [], realms: [], foreign_entries: [] } })
    renderEditor()
    await screen.findByText('pick-keytab')
    fireEvent.click(screen.getByText('pick-keytab'))
    await waitFor(() => expect(mocks.uploadKeytab).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByText('common.save'))
    await waitFor(() => expect(mocks.uploadKeytab).toHaveBeenCalledTimes(2))
    expect(mocks.uploadKeytab.mock.calls[1]).toEqual([7, mocks.picked.file])
  })
})

describe('keytab permission', () => {
  it('hides the keytab picker from a writer of profiles without write:kerberos', async () => {
    renderEditor(undefined, { canUploadKeytab: false })
    await screen.findByDisplayValue('corp')
    await loaded()
    expect(screen.getByText('common.save')).toBeInTheDocument()
    expect(screen.queryByText('pick-keytab')).toBeNull()
  })
})

describe('keytab permission lost after the pick', () => {
  it('saves the profile without storing a file chosen while the permission was held', async () => {
    mocks.uploadKeytab.mockResolvedValue({ data: { keytab_entries: [], realms: [], foreign_entries: [] } })
    const element = (props) => (
      <MemoryRouter>
        <WindowsProfileEditor profile={{ id: 7, name: 'corp' }} cas={CAS} canWrite onSaved={vi.fn()} onCancel={vi.fn()} {...props} />
      </MemoryRouter>)
    const { rerender } = render(element({ canUploadKeytab: true }))
    await screen.findByText('pick-keytab')
    fireEvent.click(screen.getByText('pick-keytab'))
    await waitFor(() => expect(mocks.uploadKeytab).toHaveBeenCalledTimes(1))
    rerender(element({ canUploadKeytab: false }))
    expect(screen.queryByText('pick-keytab')).toBeNull()
    fireEvent.click(screen.getByText('common.save'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalled())
    expect(mocks.uploadKeytab).toHaveBeenCalledTimes(1)
  })
})

describe('checklist', () => {
  const checklist = () => within(screen.getByTestId('profile-checklist'))

  it('lists what this profile still lacks', async () => {
    mocks.get.mockResolvedValue({ data: { ...PROFILE, realm: null, keytab_set: false, issuing_ca_refid: null, enabled: false } })
    renderEditor()
    await screen.findByDisplayValue('corp')
    await loaded()
    for (const key of ['realm', 'issuingCa', 'keytab', 'enabled']) {
      const row = checklist().getByText(`xcepWstep.checklist.${key}`).closest('div').parentElement
      expect(row.querySelector('.text-status-warning')).not.toBeNull()
    }
    const templates = checklist().getByText('xcepWstep.checklist.templates|count=1').closest('div').parentElement
    expect(templates.querySelector('.text-status-success')).not.toBeNull()
  })

  it('warns in the checklist when the server says the realm and the connector domain differ', async () => {
    mocks.get.mockResolvedValue({ data: { ...PROFILE, connector_id: 3, connector_domain_mismatch: true } })
    renderEditor()
    await screen.findByDisplayValue('corp')
    await loaded()
    const row = checklist().getByText('xcepWstep.checklist.connectorDomain').closest('div').parentElement
    expect(row.querySelector('.text-status-warning')).not.toBeNull()
  })

  it('judges an edited realm against the connector, not by the saved flag', async () => {
    mocks.connectors.mockResolvedValue({ data: [
      { id: 3, name: 'forest-b', realm: 'B.EXAMPLE', enabled: true, health: { state: 'up' } },
    ] })
    mocks.get.mockResolvedValue({ data: { ...PROFILE, connector_id: 3, connector_domain_mismatch: true } })
    renderEditor()
    await screen.findByDisplayValue('corp')
    await loaded()
    fireEvent.change(realmInput(), { target: { value: 'B.EXAMPLE' } })
    const row = checklist().getByText('xcepWstep.checklist.connectorDomain').closest('div').parentElement
    expect(row.querySelector('.text-status-warning')).toBeNull()
  })

  it('shows a complete profile as complete', async () => {
    renderEditor()
    await screen.findByDisplayValue('corp')
    await loaded()
    expect(screen.getByTestId('profile-checklist').querySelector('.text-status-warning')).toBeNull()
  })
})

describe('warnings', () => {
  it('warns about the default profile that names no realm', async () => {
    mocks.get.mockResolvedValue({ data: { ...PROFILE, is_default: true, realm: null, name: 'default' } })
    renderEditor({ id: 7, name: 'default' })
    expect(await screen.findByText('xcepWstep.noRealmKerberosRefused|name=default')).toBeInTheDocument()
  })

  it('warns, without blocking, when the connector serves another domain', async () => {
    mocks.connectors.mockResolvedValue({ data: [
      { id: 3, name: 'forest-b', realm: 'B.EXAMPLE', enabled: true, health: { state: 'up' } },
    ] })
    mocks.get.mockResolvedValue({ data: { ...PROFILE, connector_id: 3 } })
    renderEditor()
    expect(await screen.findByText('xcepWstep.connectorRealmDiffers|connector=B.EXAMPLE|realm=CORP.EXAMPLE')).toBeInTheDocument()
    expect(screen.getByText('common.save')).not.toBeDisabled()
  })

  it('saves a profile whose saved pair differs without sending the pair back', async () => {
    mocks.connectors.mockResolvedValue({ data: [
      { id: 3, name: 'forest-b', realm: 'B.EXAMPLE', enabled: true, health: { state: 'up' } },
    ] })
    mocks.get.mockResolvedValue({ data: { ...PROFILE, connector_id: 3 } })
    renderEditor()
    await screen.findByText('xcepWstep.connectorRealmDiffers|connector=B.EXAMPLE|realm=CORP.EXAMPLE')
    fireEvent.click(screen.getByText('common.save'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalled())
    const sent = mocks.update.mock.calls[0][1]
    expect(sent).not.toHaveProperty('connector_id')
    expect(sent).not.toHaveProperty('realm')
  })

  it('says a disabled profile refuses its machines and keeps its keys', async () => {
    mocks.get.mockResolvedValue({ data: { ...PROFILE, enabled: false } })
    renderEditor()
    expect(await screen.findByText('xcepWstep.disabledKeepsKeys')).toBeInTheDocument()
  })
})

describe('CA pickers', () => {
  it('offers only the CAs that can sign, keeps the saved one and counts the others', async () => {
    mocks.get.mockResolvedValue({ data: { ...PROFILE, issuing_ca_refid: 'ca-2' } })
    renderEditor()
    await screen.findByDisplayValue('corp')
    await loaded()
    const field = screen.getAllByTestId('field-xcepWstep.issuingCa')[0]
    const labels = within(field).getAllByRole('option').filter(o => o.value !== '').map(o => o.textContent)
    expect(labels).toEqual(['Signing CA', 'Keyless root'])
    expect(field).toHaveTextContent('cas.notListedForSigning|count=1')
  })
})

describe('shared accounts', () => {
  const field = () => screen.queryByLabelText('xcepWstep.xcepTitle: common.username')

  it('shows them for the default profile and sends them', async () => {
    mocks.get.mockResolvedValue({ data: { ...PROFILE, is_default: true } })
    renderEditor()
    await loaded()
    expect(field()).toBeInTheDocument()
    fireEvent.click(screen.getByText('common.save'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalled())
    expect(mocks.update.mock.calls[0][1]).toHaveProperty('xcep_username')
  })

  it('hides them for any other profile and does not send them', async () => {
    renderEditor()
    await loaded()
    expect(field()).toBeNull()
    fireEvent.click(screen.getByText('common.save'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalled())
    expect(mocks.update.mock.calls[0][1]).not.toHaveProperty('xcep_username')
    expect(mocks.update.mock.calls[0][1]).not.toHaveProperty('wstep_username')
  })

  it('hides them on a new profile', async () => {
    renderEditor(null)
    await loaded()
    expect(field()).toBeNull()
  })
})

describe('default profile', () => {
  const box = () => screen.queryByRole('checkbox', { name: /xcepWstep\.makeDefault/ })
  const account = () => screen.queryByLabelText('xcepWstep.xcepTitle: common.username')
  const noDefault = () => mocks.getSettings.mockResolvedValue({ data: { default_profile: null } })

  it('is offered on a new profile while none is the default, with the accounts once checked', async () => {
    noDefault()
    renderEditor(null)
    await loaded()
    await waitFor(() => expect(box()).toBeInTheDocument())
    expect(account()).toBeNull()
    fireEvent.change(screen.getByLabelText('xcepWstep.profileName'), { target: { value: 'first' } })
    fireEvent.click(box())
    fireEvent.change(account(), { target: { value: 'enroll' } })
    fireEvent.click(screen.getByText('common.save'))
    await waitFor(() => expect(mocks.create).toHaveBeenCalled())
    expect(mocks.create.mock.calls[0][0]).toMatchObject({ is_default: true, xcep_username: 'enroll' })
  })

  it('is offered on a saved profile while none is the default', async () => {
    noDefault()
    renderEditor()
    await loaded()
    await waitFor(() => expect(box()).toBeInTheDocument())
    fireEvent.click(box())
    fireEvent.click(screen.getByText('common.save'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalled())
    expect(mocks.update.mock.calls[0][1]).toMatchObject({ is_default: true })
  })

  it('is not offered once a profile is the default, and not sent', async () => {
    renderEditor()
    await loaded()
    await waitFor(() => expect(mocks.getSettings).toHaveBeenCalled())
    expect(box()).toBeNull()
    fireEvent.click(screen.getByText('common.save'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalled())
    expect(mocks.update.mock.calls[0][1]).not.toHaveProperty('is_default')
  })

  it('is not offered when the server state cannot be read', async () => {
    mocks.getSettings.mockRejectedValue(new Error('forbidden'))
    renderEditor(null)
    await loaded()
    expect(box()).toBeNull()
  })
})
