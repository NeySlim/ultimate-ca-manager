import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ updatePreferences: vi.fn() }))

vi.mock('../../services/account.service', () => ({
  accountService: { updatePreferences: mocks.updatePreferences },
}))

let store

const SERVER = { language: 'en', theme_mode: 'dark', update_popup_seen_version: '2.241' }

describe('userPreferencesStore', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    mocks.updatePreferences.mockResolvedValue({})
    vi.resetModules()
    store = await import('../userPreferencesStore')
  })

  it('holds a change made before the server prefs load, then saves it with them in one PUT', async () => {
    store.setAuthenticated(true)
    await store.persistPreference('language', 'fr')
    expect(store.getPreferences().language).toBe('fr')
    expect(mocks.updatePreferences).not.toHaveBeenCalled()

    store.applyServerPreferences(SERVER)
    const merged = { language: 'fr', theme_mode: 'dark', update_popup_seen_version: '2.241' }
    expect(store.getPreferences()).toEqual(merged)
    expect(mocks.updatePreferences).toHaveBeenCalledTimes(1)
    expect(mocks.updatePreferences).toHaveBeenCalledWith(merged)
  })

  it('drops a pending change when the user signs out before the prefs load', async () => {
    store.setAuthenticated(true)
    await store.persistPreference('language', 'fr')
    store.setAuthenticated(false)
    store.setAuthenticated(true)
    store.applyServerPreferences(SERVER)
    expect(mocks.updatePreferences).not.toHaveBeenCalled()
    expect(store.getPreferences()).toEqual(SERVER)
  })

  it('sends no PUT when the server prefs load with nothing pending', () => {
    store.setAuthenticated(true)
    store.applyServerPreferences(SERVER)
    expect(mocks.updatePreferences).not.toHaveBeenCalled()
  })

  it('saves at once, with every preference, once loaded', async () => {
    store.setAuthenticated(true)
    store.applyServerPreferences(SERVER)
    await store.persistPreference('theme_mode', 'light')
    expect(mocks.updatePreferences).toHaveBeenCalledWith({ ...SERVER, theme_mode: 'light' })
  })

  it('keeps a signed-out change local and does not replay it after sign-in', async () => {
    await store.persistPreference('language', 'de')
    store.setAuthenticated(true)
    store.applyServerPreferences(SERVER)
    expect(mocks.updatePreferences).not.toHaveBeenCalled()
    expect(store.getPreferences()).toEqual(SERVER)
  })
})
