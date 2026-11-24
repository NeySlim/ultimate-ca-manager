/**
 * The Kerberos binding of Windows enrollment works in the Docker images, except in FIPS mode,
 * where their Kerberos library does its own cryptography; a RHEL package in FIPS mode allows it.
 * Each help language says so in the Windows enrollment item of the Settings page.
 */
import { describe, it, expect } from 'vitest'
import { helpContent } from '../helpContent'
import es from '../help/es/settings'
import fr from '../help/fr/settings'
import ru from '../help/ru/settings'
import zh from '../help/zh/settings'

describe('the Windows enrollment help on Kerberos in Docker', () => {
  it.each([
    ['en', helpContent.settings],
    ['es', es.helpContent],
    ['fr', fr.helpContent],
    ['ru', ru.helpContent],
    ['zh', zh.helpContent],
  ])('%s: works in the image, refused there in FIPS mode, allowed on RHEL', (lang, content) => {
    const items = content.sections.flatMap((s) => s.items || [])
    const found = items.filter((i) => /Kerberos/.test(i.label) && /Docker/.test(i.label))
    expect(found, lang).toHaveLength(1)
    const [item] = found
    expect(item.label, lang).not.toMatch(/v2\.\d+/)
    for (const word of ['Docker', 'FIPS', 'RHEL']) expect(item.text, lang).toContain(word)
    expect(item.text, lang).not.toContain('—')
  })
})
