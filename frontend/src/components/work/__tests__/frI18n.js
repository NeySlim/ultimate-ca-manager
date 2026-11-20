/**
 * A translator over fr.json for the work queue tests: nested keys, {{name}}
 * interpolation, _one/_other plurals by count, the key itself when missing.
 */
import fr from '../../../i18n/locales/fr.json'

const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), fr)
const rules = new Intl.PluralRules('fr')

export function frT(key, arg) {
  const opts = typeof arg === 'object' && arg ? arg : {}
  let found = lookup(key)
  if (typeof opts.count === 'number') {
    const plural = lookup(`${key}_${rules.select(opts.count)}`) ?? lookup(`${key}_other`)
    if (typeof plural === 'string') found = plural
  }
  const text = typeof found === 'string' ? found : (typeof arg === 'string' ? arg : (opts.defaultValue ?? key))
  return text.replace(/\{\{(\w+)(?:, ?\w+)?\}\}/g, (_, name) => (opts[name] ?? ''))
}

export const frI18n = { t: frT, i18n: { language: 'fr', changeLanguage: () => {}, on: () => {}, off: () => {} } }
