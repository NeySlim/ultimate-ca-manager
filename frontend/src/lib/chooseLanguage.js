import { persistPreference } from '../stores/userPreferencesStore'

/** Applies a language: the interface, this browser's memory, then the account (issue #73; no-op signed out). */
export function chooseLanguage(i18n, code) {
  i18n.changeLanguage(code)
  try {
    localStorage.setItem('i18nextLng', code)
  } catch {
    // Safari private mode
  }
  persistPreference('language', code)
}
