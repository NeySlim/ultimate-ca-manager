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
    if (file === REFERENCE_LOCALE) continue
    const filePath = path.join(LOCALES_DIR, file)
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'))
    const keys = new Set(flattenKeys(data))

    const missing = [...refKeys].filter(k => !keys.has(k))
    const extra = [...keys].filter(k => !refKeys.has(k))

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

main()
