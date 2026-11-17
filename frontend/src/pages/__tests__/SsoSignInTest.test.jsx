/**
 * OIDC and SAML "Test sign-in": the report once the IdP answered (accepted, refused, expired),
 * unsaved changes announced before the test of the saved provider, and the landing page.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, vars) => (vars ? `${key} ${JSON.stringify(vars)}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const startSignInTest = vi.fn()
const getSignInTest = vi.fn()
vi.mock('../../services', () => ({
  ssoService: {
    startSignInTest: (...a) => startSignInTest(...a),
    getSignInTest: (...a) => getSignInTest(...a),
  },
}))

import SignInTestPanel, { POLL_MS } from '../settings/sso/SignInTestPanel'
import SsoTestCompletePage from '../SsoTestCompletePage'

const ACCEPTED = {
  protocol: 'oauth2', provider_enabled: false, verdict: 'accepted', stage: null, code: null,
  identity: { username: 'alice', email: 'alice@example.test', fullname: 'Alice', external_id: 'sub-1' },
  groups: ['staff'], groups_more: 0, group_source: 'the ID token and UserInfo, claims roles, groups',
  candidates: [], not_verified: [], account: { outcome: 'create', username: 'alice' },
  role: 'operator', custom_role: null,
}

const REFUSED = {
  protocol: 'saml', provider_enabled: true, verdict: 'refused', stage: 'account', code: 'sso_unmapped',
  identity: { username: 'bob', email: '', fullname: '', external_id: 'nid' },
  groups: [], groups_more: 0, group_source: "SAML attributes 'groups'",
  candidates: ['Role (role)', 'member'], not_verified: [],
  diagnosis: 'no group value was read from SAML attributes', account: { outcome: 'refused', username: null },
}

let popup
const renderPanel = (props = {}) => {
  const handleChange = vi.fn()
  render(<SignInTestPanel provider={{ id: 3 }} dirty={false} formData={{ attribute_mapping: { email: 'email' } }}
    handleChange={handleChange} {...props} />)
  return handleChange
}

const runUntilReport = async (state) => {
  getSignInTest.mockResolvedValueOnce({ data: { state: 'pending' } })
  getSignInTest.mockResolvedValueOnce({ data: state })
  await act(async () => { fireEvent.click(screen.getByText('sso.signInTest')) })
  await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS) })
  await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS) })
}

beforeEach(() => {
  vi.useFakeTimers()
  startSignInTest.mockReset().mockResolvedValue({ data: { id: 'tok', url: 'https://idp.example/authorize?state=s' } })
  getSignInTest.mockReset()
  popup = { location: { href: '' }, close: vi.fn() }
  vi.spyOn(window, 'open').mockImplementation(() => popup)
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('Test sign-in panel', () => {
  it('opens the IdP and shows an accepted report, saying the disabled provider admits nobody yet', async () => {
    renderPanel()
    await runUntilReport({ state: 'done', report: ACCEPTED })
    expect(startSignInTest).toHaveBeenCalledWith(3)
    expect(popup.location.href).toBe('https://idp.example/authorize?state=s')
    expect(getSignInTest).toHaveBeenCalledWith('tok')
    expect(screen.getByText('sso.signInTestAccepted')).toBeTruthy()
    expect(screen.getByText('operator')).toBeTruthy()
    expect(screen.getByText('sso.signInTestAccountCreate {"username":"alice"}')).toBeTruthy()
    expect(screen.getByText('sso.signInTestProviderDisabled')).toBeTruthy()
    expect(screen.getByText('staff')).toBeTruthy()
  })

  it('shows a refusal with its diagnosis and maps a received attribute to groups by its Name', async () => {
    const handleChange = renderPanel()
    await runUntilReport({ state: 'done', report: REFUSED })
    expect(screen.getByText('sso.signInTestRefused')).toBeTruthy()
    expect(screen.getByText('(sso_unmapped)')).toBeTruthy()
    expect(screen.getByText(REFUSED.diagnosis)).toBeTruthy()
    fireEvent.click(screen.getByText('sso.signInTestMapToGroups {"name":"Role (role)"}'))
    expect(handleChange).toHaveBeenCalledWith('attribute_mapping', { email: 'email', Role: 'groups' })
  })

  it('says the test expired when its report is gone', async () => {
    renderPanel()
    getSignInTest.mockRejectedValueOnce(Object.assign(new Error('Not found'), { status: 404 }))
    await act(async () => { fireEvent.click(screen.getByText('sso.signInTest')) })
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS) })
    expect(screen.getByText('sso.signInTestExpired')).toBeTruthy()
    expect(screen.queryByText('sso.signInTestAccepted')).toBeNull()
  })

  it('announces unsaved changes before testing the saved provider, and sends none of them', async () => {
    renderPanel({ dirty: true })
    await act(async () => { fireEvent.click(screen.getByText('sso.signInTest')) })
    expect(screen.getByRole('alert').textContent).toBe('sso.signInTestUnsaved')
    expect(startSignInTest).not.toHaveBeenCalled()
    expect(window.open).not.toHaveBeenCalled()
    await act(async () => { fireEvent.click(screen.getByText('sso.signInTestRunSaved')) })
    expect(startSignInTest).toHaveBeenCalledTimes(1)
    expect(startSignInTest.mock.calls[0]).toEqual([3])
  })

  it('starts nothing when the browser blocks the window', async () => {
    window.open.mockImplementation(() => null)
    renderPanel()
    await act(async () => { fireEvent.click(screen.getByText('sso.signInTest')) })
    expect(screen.getByText('sso.signInTestPopupBlocked')).toBeTruthy()
    expect(startSignInTest).not.toHaveBeenCalled()
  })

  it('is not offered before the provider is saved', () => {
    render(<SignInTestPanel provider={null} dirty={false} formData={{}} handleChange={vi.fn()} />)
    expect(screen.queryByText('sso.signInTest')).toBeNull()
  })
})

describe('Sign-in test landing page', () => {
  it.each([
    ['done', 'sso.signInTestCompleteDone'],
    ['used', 'sso.signInTestCompleteUsed'],
    ['other_browser', 'sso.signInTestCompleteOtherBrowser'],
    ['anything', 'sso.signInTestCompleteExpired'],
  ])('says what became of the test (%s), never the application', (result, key) => {
    render(<MemoryRouter initialEntries={[`/sso-test-complete?result=${result}`]}><SsoTestCompletePage /></MemoryRouter>)
    expect(screen.getByText(key)).toBeTruthy()
    expect(screen.getByText('sso.signInTestCompleteBack').closest('a').getAttribute('href')).toBe('/settings?tab=sso')
  })
})
