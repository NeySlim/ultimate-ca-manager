/** Why the server would refuse an approval decision is told in the reader's language, not in English. */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const dir = dirname(fileURLToPath(import.meta.url))
const load = (code) => JSON.parse(readFileSync(join(dir, '..', 'locales', `${code}.json`), 'utf8'))
const en = load('en').approvals.work.cannot

describe('the refusal reasons of an approval', () => {
  for (const code of ['de', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'uk', 'zh']) {
    it(`${code}: translates each reason`, () => {
      const reasons = load(code).approvals.work.cannot
      for (const key of ['own_request', 'not_in_group', 'already_voted']) {
        expect(reasons[key], key).toBeTruthy()
        expect(reasons[key], key).not.toBe(en[key])
      }
    })
  }
})
