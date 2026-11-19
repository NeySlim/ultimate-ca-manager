#!/usr/bin/env node
/**
 * i18n Sync Checker — verifies all locale files have identical key structures.
 * Run: node scripts/check-i18n-sync.js
 * Exit code 0 = all in sync, 1 = missing keys found
 */
const fs = require('fs')
const path = require('path')

const LOCALES_DIR = path.join(__dirname, '../frontend/src/i18n/locales')
const REFERENCE_LOCALE = 'en.json'

function flattenKeys(obj, prefix = '') {
  const keys = []
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      keys.push(...flattenKeys(value, fullKey))
    } else {
      keys.push(fullKey)
    }
  }
  return keys
}

// Plural forms a language needs beyond English's one/other (CLDR), e.g.
// Ukrainian few/many: allowed on a key plural in the reference, and only
// when the language has that category
const EXTRA_PLURAL = /^(.*)_(zero|two|few|many)$/

function isLocalePluralForm(key, refKeys, categories) {
  const m = key.match(EXTRA_PLURAL)
  return Boolean(m) && categories.includes(m[2])
    && (refKeys.has(`${m[1]}_one`) || refKeys.has(`${m[1]}_other`))
}

// A language with a "few" form (Slavic) must give few and many on every
// plural key, or ordinary counts fall back to English. The "many" of French
// or Spanish only covers millions and is not required.
function missingPluralForms(keys, refKeys, categories) {
  if (!categories.includes('few')) return []
  const needed = categories.filter(c => c === 'few' || c === 'many')
  const bases = [...refKeys].filter(k => k.endsWith('_one')).map(k => k.slice(0, -4))
  return bases.flatMap(b => needed.map(c => `${b}_${c}`)).filter(k => !keys.has(k))
}

// JSON.parse keeps the last of two equal keys in one object; scan the text so
// the earlier (often translated) value is not silently lost.
function findDuplicateKeys(text) {
  const dups = []
  const stack = [] // per open container: Set of keys, or null for an array
  const path = []
  let i = 0
  const readString = () => {
    let j = i + 1
    while (text[j] !== '"') j += text[j] === '\\' ? 2 : 1
    const raw = text.slice(i, j + 1)
    i = j + 1
    return JSON.parse(raw)
  }
  let expectKey = false
  while (i < text.length) {
    const c = text[i]
    if (c === '{') { stack.push(new Set()); expectKey = true; i++ }
    else if (c === '[') { stack.push(null); expectKey = false; i++ }
    else if (c === '}' || c === ']') { stack.pop(); if (stack[stack.length - 1] instanceof Set) path.pop(); expectKey = false; i++ }
    else if (c === ',') { expectKey = stack[stack.length - 1] instanceof Set; i++ }
    else if (c === '"') {
      const str = readString()
      const top = stack[stack.length - 1]
      if (expectKey && top instanceof Set) {
        if (top.has(str)) dups.push([...path.filter(Boolean), str].join('.'))
        top.add(str)
        path.push(str)
        expectKey = false
        // the value follows the colon; a scalar value pops its path entry
        while (/\s/.test(text[i])) i++
        i++ // ':'
        while (/\s/.test(text[i])) i++
        if (text[i] !== '{' && text[i] !== '[') {
          if (text[i] === '"') readString()
          else while (!/[,}\]\s]/.test(text[i])) i++
          path.pop()
        } else {
          // container pushes its own frame; its closing pops this key
        }
      }
    } else i++
  }
  return dups
}

function main() {
  const files = fs.readdirSync(LOCALES_DIR).filter(f => f.endsWith('.json'))
  if (files.length === 0) {
    console.error('❌ No locale files found')
    process.exit(1)
  }

  // Load reference
  const refPath = path.join(LOCALES_DIR, REFERENCE_LOCALE)
  const refData = JSON.parse(fs.readFileSync(refPath, 'utf8'))
  const refKeys = new Set(flattenKeys(refData))

  console.log(`📋 Reference: ${REFERENCE_LOCALE} (${refKeys.size} keys)`)
  console.log(`📂 Checking ${files.length} locale files...\n`)

  let hasErrors = false

  for (const file of files) {
    const filePath = path.join(LOCALES_DIR, file)
    const text = fs.readFileSync(filePath, 'utf8')
    const dupKeys = findDuplicateKeys(text)
    if (dupKeys.length > 0) {
      hasErrors = true
      console.log(`  ❌ ${file} — duplicate keys in one object:`)
      dupKeys.slice(0, 10).forEach(k => console.log(`       - ${k}`))
    }
    if (file === REFERENCE_LOCALE) continue
    const data = JSON.parse(text)
    const keys = new Set(flattenKeys(data))

    const categories = new Intl.PluralRules(file.replace(/\.json$/, '')).resolvedOptions().pluralCategories
    const missing = [...refKeys].filter(k => !keys.has(k))
      .concat(missingPluralForms(keys, refKeys, categories))
    const extra = [...keys].filter(k => !refKeys.has(k) && !isLocalePluralForm(k, refKeys, categories))

    if (missing.length === 0 && extra.length === 0) {
      console.log(`  ✅ ${file} — ${keys.size} keys (in sync)`)
    } else {
      hasErrors = true
      console.log(`  ❌ ${file} — ${keys.size} keys`)
      if (missing.length > 0) {
        console.log(`     Missing (${missing.length}):`)
        missing.slice(0, 10).forEach(k => console.log(`       - ${k}`))
        if (missing.length > 10) console.log(`       ... and ${missing.length - 10} more`)
      }
      if (extra.length > 0) {
        console.log(`     Extra (${extra.length}):`)
        extra.slice(0, 10).forEach(k => console.log(`       - ${k}`))
        if (extra.length > 10) console.log(`       ... and ${extra.length - 10} more`)
      }
    }
  }

  console.log('')
  if (hasErrors) {
    console.log('❌ i18n keys are OUT OF SYNC — fix before committing!')
    process.exit(1)
  } else {
    console.log('✅ All locale files are in sync')
    process.exit(0)
  }
}

if (require.main === module) main()

module.exports = { findDuplicateKeys, flattenKeys, isLocalePluralForm, missingPluralForms }
