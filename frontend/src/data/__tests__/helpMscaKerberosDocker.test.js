/**
 * Kerberos to a Microsoft CA works in the Docker images; only FIPS mode refuses it there, since
 * their Kerberos library does its own cryptography, while a RHEL package in FIPS mode allows it.
 * Each help language says so in the Kerberos warning of the Microsoft CA page.
 */
import { describe, it, expect } from 'vitest'
import { helpContent } from '../helpContent'
import es from '../help/es/msca'
import fr from '../help/fr/msca'
import ru from '../help/ru/msca'
import zh from '../help/zh/msca'

const NOT_IN_DOCKER = [/not available in Docker/i, /non disponible dans Docker/i, /no disponible en Docker/i,
  /в Docker недоступен/i, /在 Docker 中不可用/]

describe('the Microsoft CA help on Kerberos in Docker', () => {
  it.each([
    ['en', helpContent.msca],
    ['es', es.helpContent],
    ['fr', fr.helpContent],
    ['ru', ru.helpContent],
    ['zh', zh.helpContent],
  ])('%s: available in the image, refused there in FIPS mode, allowed on RHEL', (lang, content) => {
    const warning = content.warnings.find((w) => w.startsWith('Kerberos'))
    expect(warning, lang).toBeTruthy()
    for (const wrong of NOT_IN_DOCKER) expect(warning, lang).not.toMatch(wrong)
    for (const word of ['Docker', 'FIPS', 'RHEL']) expect(warning, lang).toContain(word)
    expect(warning, lang).not.toContain('—')
  })
})
