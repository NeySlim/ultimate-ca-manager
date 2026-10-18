import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  getPreferences: vi.fn(),
  updatePreferences: vi.fn(),
  i18n: { language: 'en', changeLanguage: vi.fn() },
}))

vi.mock('../../services/auth.service', () => ({
  authService: { getCurrentUser: mocks.getCurrentUser, login: mocks.login, logout: vi.fn() },
}))

vi.mock('../../services/account.service', () => ({
  accountService: { getPreferences: mocks.getPreferences, updatePreferences: mocks.updatePreferences },
}))

vi.mock('../../i18n', () => ({ default: mocks.i18n }))

import { AuthProvider, useAuth } from '../AuthContext'
import {
  arePreferencesLoaded, getPreferences, persistPreference, setAuthenticated,
} from '../../stores/userPreferencesStore'

const SERVER = { language: 'en', theme_mode: 'dark' }

let auth
function Probe() {
  auth = useAuth()
  return null
}

const deferred = () => {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  return { promise, resolve }
}

async function mountSignedOut() {
  render(<AuthProvider><Probe /></AuthProvider>)
  await waitFor(() => expect(auth.loading).toBe(false))
}

describe('AuthContext and the preferences store', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setAuthenticated(false)
    mocks.i18n.language = 'en'
    mocks.updatePreferences.mockResolvedValue({})
    mocks.getCurrentUser.mockRejectedValue(Object.assign(new Error('no session'), { status: 401 }))
    mocks.login.mockResolvedValue({ data: { user: { id: 1, username: 'admin' }, permissions: ['*'], role: 'admin' } })
  })

  it('keeps the language chosen while the login prefs load, in i18n and on the server', async () => {
    await mountSignedOut()
    const prefs = deferred()
    mocks.getPreferences.mockReturnValue(prefs.promise)

    let done
    act(() => { done = auth.login('admin', 'pw') })
    await waitFor(() => expect(mocks.getPreferences).toHaveBeenCalled())
    // What the language menu does: switch i18n, then persist.
    mocks.i18n.language = 'fr'
    await act(async () => { await persistPreference('language', 'fr') })
    expect(mocks.updatePreferences).not.toHaveBeenCalled()

    await act(async () => { prefs.resolve({ data: SERVER }); await done })
    expect(mocks.i18n.changeLanguage).not.toHaveBeenCalledWith('en')
    expect(getPreferences().language).toBe('fr')
    expect(mocks.updatePreferences).toHaveBeenCalledWith({ language: 'fr', theme_mode: 'dark' })
  })

  it('keeps a pending language when a session restore applies the prefs', async () => {
    setAuthenticated(true)
    mocks.i18n.language = 'fr'
    await persistPreference('language', 'fr')
    mocks.getCurrentUser.mockResolvedValue({
      data: { authenticated: true, user: { id: 1, username: 'admin' }, permissions: ['*'], preferences: SERVER },
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(auth.isAuthenticated).toBe(true))
    expect(mocks.i18n.changeLanguage).not.toHaveBeenCalledWith('en')
    expect(getPreferences().language).toBe('fr')
  })

  it('applies the server language when nothing was changed meanwhile', async () => {
    mocks.i18n.language = 'de'
    await mountSignedOut()
    mocks.getPreferences.mockResolvedValue({ data: SERVER })
    await act(async () => { await auth.login('admin', 'pw') })
    expect(mocks.i18n.changeLanguage).toHaveBeenCalledWith('en')
  })

  it('resets the store when a session check answers 401', async () => {
    mocks.getCurrentUser.mockResolvedValueOnce({
      data: { authenticated: true, user: { id: 1, username: 'admin' }, permissions: ['*'], preferences: SERVER },
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(auth.isAuthenticated).toBe(true))
    expect(arePreferencesLoaded()).toBe(true)

    await act(async () => { await auth.checkSession() })
    expect(auth.isAuthenticated).toBe(false)
    expect(arePreferencesLoaded()).toBe(false)
    expect(getPreferences()).toEqual({})
  })

  it('retries the prefs load once when it fails at login', async () => {
    await mountSignedOut()
    mocks.getPreferences
      .mockRejectedValueOnce(new Error('blip'))
      .mockResolvedValueOnce({ data: SERVER })
    await act(async () => { await auth.login('admin', 'pw') })
    expect(mocks.getPreferences).toHaveBeenCalledTimes(2)
    expect(arePreferencesLoaded()).toBe(true)
    expect(getPreferences()).toEqual(SERVER)
  })

  it('still signs in when both loads fail, and saves nothing', async () => {
    await mountSignedOut()
    mocks.getPreferences.mockRejectedValue(new Error('down'))
    await act(async () => { await auth.login('admin', 'pw') })
    expect(auth.isAuthenticated).toBe(true)
    expect(arePreferencesLoaded()).toBe(false)
    await act(async () => { await persistPreference('language', 'fr') })
    expect(mocks.updatePreferences).not.toHaveBeenCalled()
  })
})
