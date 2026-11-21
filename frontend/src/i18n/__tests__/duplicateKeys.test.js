import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
const { findDuplicateKeys } = require('../../../../scripts/check-i18n-sync.js')

describe('duplicate keys in one JSON object', () => {
  it('reports a key repeated inside the same object', () => {
    const text = '{"tools": {"a": "x", "b": {"c": 1, "d": [{"e": 1, "e": 2}]}, "a": "y"}, "z": "\\"a\\": 1"}'
    expect(findDuplicateKeys(text)).toEqual(['tools.b.d.e', 'tools.a'])
  })

  it('accepts the same name in different objects', () => {
    expect(findDuplicateKeys('{"a": {"k": 1}, "b": {"k": 2}, "c": [{"k": 1}, {"k": 2}]}')).toEqual([])
  })

  it('makes the checker fail on a locale file with a duplicate', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'i18n-dup-'))
    try {
      const real = path.join(__dirname, '../locales/en.json')
      const text = fs.readFileSync(real, 'utf8').replace('"tools": {', '"tools": {\n    "keyPasswordPlaceholder": "dup",')
      fs.writeFileSync(path.join(dir, 'en.json'), text)
      const script = fs.readFileSync(path.join(__dirname, '../../../../scripts/check-i18n-sync.js'), 'utf8')
        .replace("path.join(__dirname, '../frontend/src/i18n/locales')", JSON.stringify(dir))
      fs.writeFileSync(path.join(dir, 'check.js'), script)
      const r = spawnSync('node', [path.join(dir, 'check.js')], { encoding: 'utf8' })
      expect(r.status).toBe(1)
      expect(r.stdout).toContain('tools.keyPasswordPlaceholder')
    } finally {
      fs.rmSync(dir, { recursive: true, force: true })
    }
  })

  it('finds no duplicate in the shipped locale files', () => {
    const dir = path.join(__dirname, '../locales')
    for (const f of fs.readdirSync(dir)) {
      expect(findDuplicateKeys(fs.readFileSync(path.join(dir, f), 'utf8')), f).toEqual([])
    }
  })
})
