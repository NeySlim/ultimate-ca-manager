import { describe, it, expect } from 'vitest'
import { soleLegendsOff } from '../atelierParts'

describe('a settings card names its lone group once', () => {
  it('drops the legend of a lone group that repeats the card title, keeps the others', () => {
    const sections = soleLegendsOff([
      { id: 'a', label: 'Serveur ACME local', groups: [{ legend: 'Serveur ACME local', fields: [] }] },
      { id: 'b', label: 'Client', groups: [{ legend: 'Client', fields: [] }, { legend: 'Contrôles DNS-01', fields: [] }] },
      { id: 'c', label: 'Service', groups: [{ legend: 'Paramètres du serveur', fields: [] }] },
      { id: 'd', label: 'Profils', groups: [] },
    ])
    expect(sections.map((s) => s.groups.map((g) => g.legend))).toEqual([
      [undefined], ['Client', 'Contrôles DNS-01'], ['Paramètres du serveur'], [],
    ])
  })
})
