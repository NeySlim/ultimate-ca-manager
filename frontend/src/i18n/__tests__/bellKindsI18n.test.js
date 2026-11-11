import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { BELL_KINDS, FAILURE_ACTIONS, SESSION_ACTIONS } from '../../components/shell/notifications'

const localesDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'locales')
const LOCALE_CODES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'uk', 'zh']

describe('bell kind labels (9 locales)', () => {
  for (const code of LOCALE_CODES) {
    it(`${code}: every kind the bell can show has a label`, () => {
      const kinds = JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8')).shell?.bell?.kinds || {}
      for (const kind of [...BELL_KINDS, ...FAILURE_ACTIONS, ...SESSION_ACTIONS]) {
        expect(String(kinds[kind] || '').trim(), `shell.bell.kinds.${kind} in ${code}`).not.toBe('')
      }
    })
  }
})
