// The font registry the release SBOM reads says what each font file says of itself.
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import crypto from 'crypto'
import { woff2Names } from './woff2-name.js'

const FRONTEND = path.resolve(__dirname, '..')
const registry = JSON.parse(fs.readFileSync(path.resolve(FRONTEND, '../scripts/ci/sbom-data/fonts.json'), 'utf8'))
const fontsDir = path.join(FRONTEND, 'public', 'fonts')
const OFL = 'This Font Software is licensed under the SIL Open Font License, Version 1.1.'

describe('font registry', () => {
  const files = fs.readdirSync(fontsDir).filter(f => /\.(woff2?|ttf|otf)$/.test(f)).sort()

  it('lists every shipped font file once, by its hash', () => {
    expect(registry.fonts.map(f => f.file).sort()).toEqual(files.map(f => `fonts/${f}`))
    for (const entry of registry.fonts) {
      const bytes = fs.readFileSync(path.join(FRONTEND, 'public', entry.file))
      expect(crypto.createHash('sha256').update(bytes).digest('hex')).toBe(entry.sha256)
    }
  })

  it.each(registry.fonts.map(f => [f.file, f]))('%s: version, name, copyright and license from its name table', (_file, entry) => {
    const names = woff2Names(fs.readFileSync(path.join(FRONTEND, 'public', entry.file)))
    expect(names[6]).toBe(entry.postscript_name)
    expect(names[5].replace(/^Version /, '').split(';')[0]).toBe(entry.version)
    expect(names[0]).toBe(entry.copyright)
    expect(entry.license).toBe('OFL-1.1')
    expect(names[13]).toContain(OFL)
  })

  it('ships each license text next to the fonts', () => {
    for (const entry of registry.fonts) {
      const text = fs.readFileSync(path.join(FRONTEND, 'public', entry.license_file), 'utf8')
      expect(text).toContain('SIL OPEN FONT LICENSE Version 1.1')
    }
  })

  it('refuses a file that is not WOFF2', () => {
    expect(() => woff2Names(Buffer.from('wOFFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'))).toThrow('not a WOFF2')
  })
})
