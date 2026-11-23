/**
 * The HSM page counts what its button creates and its search finds: providers, in every language,
 * never « locations » in the head and « provider » in the button.
 */
import { describe, it, expect } from 'vitest'
import en from '../locales/en.json'
import fr from '../locales/fr.json'
import de from '../locales/de.json'
import es from '../locales/es.json'

const KEYS = ['unit_one', 'unit_other', 'range_one', 'range_other']

describe('HSM count', () => {
  it.each([[en, /provider/i], [fr, /fournisseur/i], [de, /anbieter/i], [es, /proveedor/i]])('names providers, as the button does (%#)', (locale, word) => {
    expect(locale.hsm.newProvider).toMatch(word)
    for (const key of KEYS) expect(locale.hsm[key]).toMatch(word)
  })
})
