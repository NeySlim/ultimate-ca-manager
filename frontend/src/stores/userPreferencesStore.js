/**
 * userPreferencesStore — central pub/sub for server-persisted user prefs.
 *
 * Issue #73: language + theme were lost on every login because they only
 * lived in localStorage. This store is the bridge between AuthContext
 * (which fetches preferences from the server) and the contexts that
 * actually apply them (ThemeContext, LanguageSelector).
 *
 * Flow:
 *   1. AuthContext receives prefs from /auth/verify or /account/preferences
 *      and calls applyServerPreferences(prefs).
 *   2. Subscribers (ThemeContext useEffect, i18n bootstrap) react to
 *      the change and update their local state + the DOM.
 *   3. When a user changes a setting, the relevant component calls
 *      persistPreference(key, value) which (a) pushes into this store
 *      and (b) PUTs to /account/preferences when authenticated.
 */
import { accountService } from '../services/account.service'

let _prefs = {}
let _authenticated = false
// True once the server copy has been applied: a PUT before that would erase it.
let _loaded = false
// Keys changed while signed in but before the server copy arrived.
let _pendingKeys = new Set()
const _listeners = new Set()

function _notify() {
  for (const cb of _listeners) {
    try { cb(_prefs) } catch { /* swallow listener errors */ }
  }
}

export function getPreferences() {
  return { ..._prefs }
}

export function arePreferencesLoaded() {
  return _loaded
}

export function subscribePreferences(cb) {
  _listeners.add(cb)
  return () => _listeners.delete(cb)
}

export function setAuthenticated(value) {
  _authenticated = !!value
  if (!_authenticated) {
    _prefs = {}
    _loaded = false
    _pendingKeys = new Set()
    _notify()
  }
}

/**
 * Apply a server-provided preferences object (replaces local state).
 * Called by AuthContext after login / verify succeeds.
 */
export function applyServerPreferences(prefs) {
  if (!prefs || typeof prefs !== 'object') return
  const local = _prefs
  const pending = _pendingKeys
  _pendingKeys = new Set()
  _prefs = { ...prefs }
  // Changes made while loading win over the server copy, then go out in one full PUT.
  for (const key of pending) _prefs[key] = local[key]
  _loaded = true
  _notify()
  if (pending.size && _authenticated) _save()
}

async function _save() {
  try {
    await accountService.updatePreferences(_prefs)
  } catch {
    // Network / backend failure — silent: local state still applies.
    // Next login will fall back to server-side value (the prior one).
  }
}

/**
 * Update one preference and persist server-side when authenticated.
 * Always updates the local store so subscribers react immediately.
 * The PUT replaces the whole object, so it waits for the server copy.
 */
export async function persistPreference(key, value) {
  _prefs = { ..._prefs, [key]: value }
  _notify()
  if (!_authenticated) return
  if (!_loaded) {
    _pendingKeys.add(key)
    return
  }
  await _save()
}
