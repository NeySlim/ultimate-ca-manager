/**
 * The English strings of en.json for tests that read what a page says: interpolation, the
 * {{x, number}} format, the _one/_other plurals and a default value, as i18next does them.
 */
import en from '../i18n/locales/en.json'

const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), en)

export function enT(key, opts) {
  const vars = typeof opts === 'object' && opts ? opts : {}
  let template = lookup(key)
  if (typeof vars.count === 'number') {
    const plural = lookup(`${key}_${vars.count === 1 ? 'one' : 'other'}`)
    if (typeof plural === 'string') template = plural
  }
  if (typeof template !== 'string') return typeof opts === 'string' ? opts : (vars.defaultValue ?? key)
  return template.replace(/\{\{\s*(\w+)(?:,\s*\w+)?\s*\}\}/g, (_m, name) => String(vars[name] ?? `{{${name}}}`))
}

export const enI18n = { t: enT, i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} } }
