/**
 * OIDC and SAML "Test sign-in": the report once the IdP answered (accepted, refused, expired),
 * unsaved changes announced before the test of the saved provider, and the landing page.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { StrictMode } from 'react'
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

import SignInTestPanel, { LAUNCH_MS, POLL_MS } from '../settings/sso/SignInTestPanel'
import SsoTestCompletePage, { CLOSE_DELAY_MS } from '../SsoTestCompletePage'
import SsoTestLaunchPage from '../SsoTestLaunchPage'
import { CHANNEL, LAUNCH_PATH } from '../settings/sso/signInTestChannel'

// Same-origin BroadcastChannel, delivered at once to every other open channel of the name.
class FakeChannel {
  static open = []
  static posted = []
  constructor(name) {
    this.name = name
    this.onmessage = null
    this.closed = false
    FakeChannel.open.push(this)
  }
  postMessage(data) {
    FakeChannel.posted.push(data)
    for (const c of FakeChannel.open) {
      if (c !== this && !c.closed && c.name === this.name) c.onmessage?.({ data })
    }
  }
  close() { this.closed = true }
}

// What the test window does: says it is ready with the key of its URL, records what it is sent.
const testWindow = () => {
  const [path, key] = window.open.mock.calls.at(-1)[0].split('#')
  expect(path).toBe(LAUNCH_PATH)
  const channel = new FakeChannel(CHANNEL)
  const got = []
  channel.onmessage = ({ data }) => got.push(data)
  channel.postMessage({ type: 'ready', key })
  return { key, got }
}

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

const renderPanel = (props = {}) => {
  const handleChange = vi.fn()
  render(<SignInTestPanel provider={{ id: 3 }} dirty={false} formData={{ attribute_mapping: { email: 'email' } }}
    handleChange={handleChange} {...props} />)
  return handleChange
}

const launch = async () => {
  await act(async () => { fireEvent.click(screen.getByText('sso.signInTest')) })
  let win
  await act(async () => { win = testWindow() })
  return win
}

const runUntilReport = async (state) => {
  getSignInTest.mockResolvedValueOnce({ data: { state: 'pending' } })
  getSignInTest.mockResolvedValueOnce({ data: state })
  const win = await launch()
  await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS) })
  await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS) })
  return win
}

beforeEach(() => {
  vi.useFakeTimers()
  startSignInTest.mockReset().mockResolvedValue({ data: { id: 'tok', url: 'https://idp.example/authorize?state=s' } })
  getSignInTest.mockReset()
  FakeChannel.open = []
  FakeChannel.posted = []
  vi.stubGlobal('BroadcastChannel', FakeChannel)
  vi.spyOn(window, 'open').mockImplementation(() => null) // what noopener returns
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Test sign-in panel', () => {
  it('opens the IdP and shows an accepted report, saying the disabled provider admits nobody yet', async () => {
    renderPanel()
    const win = await runUntilReport({ state: 'done', report: ACCEPTED })
    expect(startSignInTest).toHaveBeenCalledWith(3)
    expect(win.got).toContainEqual({ type: 'go', key: win.key, url: 'https://idp.example/authorize?state=s' })
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
    await launch()
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
    await act(async () => { testWindow() })
    expect(startSignInTest).toHaveBeenCalledTimes(1)
    expect(startSignInTest.mock.calls[0]).toEqual([3])
  })

  it('starts nothing when the test window never opens', async () => {
    renderPanel()
    await act(async () => { fireEvent.click(screen.getByText('sso.signInTest')) })
    await act(async () => { await vi.advanceTimersByTimeAsync(LAUNCH_MS) })
    expect(screen.getByText('sso.signInTestPopupBlocked')).toBeTruthy()
    expect(startSignInTest).not.toHaveBeenCalled()
  })

  it('opens the test window with noopener and noreferrer, the IdP URL sent on the channel', async () => {
    renderPanel()
    await act(async () => { fireEvent.click(screen.getByText('sso.signInTest')) })
    const [, target, features] = window.open.mock.calls[0]
    expect(target).toBe('_blank')
    expect(features.split(',')).toEqual(expect.arrayContaining(['noopener', 'noreferrer']))
    expect(startSignInTest).not.toHaveBeenCalled() // nothing starts before the window is there
    const win = await act(async () => testWindow())
    expect(startSignInTest).toHaveBeenCalledTimes(1)
    expect(win.got).toEqual([{ type: 'go', key: win.key, url: 'https://idp.example/authorize?state=s' }])
  })

  it('answers no window but its own', async () => {
    renderPanel()
    await act(async () => { fireEvent.click(screen.getByText('sso.signInTest')) })
    const stranger = new FakeChannel(CHANNEL)
    await act(async () => { stranger.postMessage({ type: 'ready', key: 'not-the-key' }) })
    expect(startSignInTest).not.toHaveBeenCalled()
  })

  it('learns the end from the test window, without an opener, before the next poll', async () => {
    renderPanel()
    getSignInTest.mockResolvedValueOnce({ data: { state: 'done', report: ACCEPTED } })
    await launch()
    await act(async () => { new FakeChannel(CHANNEL).postMessage({ type: 'complete', result: 'done' }) })
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(getSignInTest).toHaveBeenCalledTimes(1)
    expect(screen.getByText('sso.signInTestAccepted')).toBeTruthy()
  })

  it('can be started again while it waits, which drops the wait in progress', async () => {
    renderPanel()
    startSignInTest.mockResolvedValueOnce({ data: { id: 'first', url: 'https://idp.example/a' } })
    await launch()
    const button = screen.getByText('sso.signInTest').closest('button')
    expect(button.disabled).toBe(false)
    getSignInTest.mockResolvedValue({ data: { state: 'pending' } })
    const second = await launch()
    expect(window.open).toHaveBeenCalledTimes(2)
    expect(second.got.at(-1)).toMatchObject({ type: 'go', url: 'https://idp.example/authorize?state=s' })
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS * 3) })
    expect(getSignInTest.mock.calls.map((c) => c[0])).not.toContain('first')
    expect(getSignInTest).toHaveBeenCalledWith('tok')
  })

  it('gives the hand back on cancel, and polls no more', async () => {
    renderPanel()
    await launch()
    await act(async () => { fireEvent.click(screen.getByText('sso.signInTestCancel')) })
    expect(screen.queryByText('sso.signInTestWaiting')).toBeNull()
    expect(screen.queryByText('sso.signInTestCancel')).toBeNull()
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS * 3) })
    expect(getSignInTest).not.toHaveBeenCalled()
  })

  it('tells a window still opening to stop when it is cancelled', async () => {
    renderPanel()
    await act(async () => { fireEvent.click(screen.getByText('sso.signInTest')) })
    const key = window.open.mock.calls[0][0].split('#')[1]
    await act(async () => { fireEvent.click(screen.getByText('sso.signInTestCancel')) })
    expect(FakeChannel.posted).toContainEqual({ type: 'abort', key })
    await act(async () => { testWindow() })
    expect(startSignInTest).not.toHaveBeenCalled()
  })

  it('shows the report under StrictMode, whose effects mount twice', async () => {
    render(<StrictMode><SignInTestPanel provider={{ id: 3 }} dirty={false} formData={{}} handleChange={vi.fn()} /></StrictMode>)
    await runUntilReport({ state: 'done', report: ACCEPTED })
    expect(screen.getByText('sso.signInTestAccepted')).toBeTruthy()
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
    expect(FakeChannel.posted).toEqual([{ type: 'complete', result: key === 'sso.signInTestCompleteExpired' ? 'expired' : result }])
  })

  it('asks the user to close the window when the browser keeps it open', async () => {
    vi.spyOn(window, 'close').mockImplementation(() => {})
    render(<MemoryRouter initialEntries={['/sso-test-complete?result=done']}><SsoTestCompletePage /></MemoryRouter>)
    expect(screen.queryByText('sso.signInTestCompleteClose')).toBeNull()
    await act(async () => { await vi.advanceTimersByTimeAsync(CLOSE_DELAY_MS + 500) })
    expect(window.close).toHaveBeenCalled()
    expect(screen.getByText('sso.signInTestCompleteClose')).toBeTruthy()
  })
})

describe('Sign-in test window', () => {
  const realLocation = window.location
  afterEach(() => { window.location = realLocation })

  const openAt = (hash) => {
    delete window.location
    window.location = { hash, replace: vi.fn() }
    render(<SsoTestLaunchPage />)
  }

  it('says it is ready under its key, then goes to the IdP URL it is sent', async () => {
    const panelSide = new FakeChannel(CHANNEL)
    const heard = []
    panelSide.onmessage = ({ data }) => heard.push(data)
    openAt('#k1')
    expect(heard).toEqual([{ type: 'ready', key: 'k1' }])
    await act(async () => { panelSide.postMessage({ type: 'go', key: 'other', url: 'https://evil.example/' }) })
    expect(window.location.replace).not.toHaveBeenCalled()
    await act(async () => { panelSide.postMessage({ type: 'go', key: 'k1', url: 'https://idp.example/authorize?state=s' }) })
    expect(window.location.replace).toHaveBeenCalledWith('https://idp.example/authorize?state=s')
  })

  it('follows no URL but http(s)', async () => {
    const panelSide = new FakeChannel(CHANNEL)
    openAt('#k2')
    await act(async () => { panelSide.postMessage({ type: 'go', key: 'k2', url: 'javascript:alert(1)' }) })
    expect(window.location.replace).not.toHaveBeenCalled()
    expect(screen.getByText('sso.signInTestFailed')).toBeTruthy()
  })
})
