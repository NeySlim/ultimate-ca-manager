/**
 * French text writes the elision with the typographic apostrophe (l’AC, d’un), as the Atelier;
 * a straight quote stays only around a literal the user types ('superseded', 'viewer').
 */
import { describe, expect, it } from 'vitest'
import fr from '../locales/fr.json'

const help = import.meta.glob('../../data/help/fr/*.js', { eager: true })

const strings = (node, path = '') => (typeof node === 'string' ? [[path, node]]
  : node === null || typeof node !== 'object' ? []
  : Object.entries(node).flatMap(([k, v]) => strings(v, path ? `${path}.${k}` : k)))

describe('French apostrophes', () => {
  it('no elision is written with a straight quote', () => {
    const straight = strings(fr).filter(([, v]) => /[A-Za-zÀ-ÿ]'[A-Za-zÀ-ÿ]/.test(v)).map(([p]) => p)
    expect(straight).toEqual([])
  })

  it('the French help writes it the same way, so it quotes the screens word for word', () => {
    const straight = Object.entries(help).flatMap(([file, mod]) => strings(mod, file))
      .filter(([, v]) => /[A-Za-zÀ-ÿ]'[A-Za-zÀ-ÿ]/.test(v)).map(([p]) => p)
    expect(straight).toEqual([])
  })
})
