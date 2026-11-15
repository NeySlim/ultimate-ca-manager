/**
 * Every "A > B" path the guides give names a place the console has: a group and a module of
 * the Modules menu (read from the navigation registry), or a tab of the Settings page. The user
 * guide must also name every page of the menu by its full path, and links to guide headings
 * must land on a heading that exists.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { GROUPS, MODULES } from '../navigation/registry'
import en from '../i18n/locales/en.json'

const docsDir = path.resolve(__dirname, '../../../docs')
const lookup = (key) => key.split('.').reduce((o, k) => (o == null ? o : o[k]), en)

const groupLabel = Object.fromEntries(GROUPS.map(g => [g.id, lookup(g.labelKey)]))
const moduleLabels = (m) => [lookup(m.labelKey), m.shortKey && lookup(m.shortKey)].filter(Boolean)
const settingsTabs = Object.values(en.settings.tabs)
const accountTabs = [en.account.profile, en.common.security, en.account.apiKeys]

// The longest label (or module id) the element starts with, as a whole word
function leading(element, labels) {
  const hits = labels.filter(l => element === l || element.startsWith(l + ' '))
  return hits.sort((a, b) => b.length - a.length)[0]
}

// Roots the earlier console had and this one has not: a path under one of them is always stale
const GONE = ['System', 'Admin', 'Dashboard']
const ROOTS = ['Modules', ...GONE, ...Object.values(groupLabel), ...MODULES.flatMap(moduleLabels)]
  .sort((a, b) => b.length - a.length)
const ROOT_RE = new RegExp(`(?:^|[^\\w])(${ROOTS.map(r => r.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')).join('|')})((?:\\s*(?:>|→)\\s*[A-Z][^>→()\`*,.;:|\\n]*)+)`, 'g')

// Paths of another product's console, quoted by an integration guide
const ELSEWHERE = ['Templates > SCEP certificate']

export function pathsIn(markdown) {
  const prose = markdown.replace(/^```.*?^```/gms, '').replace(/\*\*|`/g, '')
  return [...prose.matchAll(ROOT_RE)].map(m => [m[1], ...m[2].split(/\s*(?:>|→)\s*/).filter(Boolean).map(s => s.trim())])
}

export function problemsWith(steps) {
  const [root, ...rest] = steps
  const second = rest[0]
  if (GONE.includes(root)) return `${root} is not a place of this console`
  if (root === 'Modules') {
    const group = GROUPS.find(g => groupLabel[g.id] === second)
    if (!group) return `${second} is not a group of the Modules menu`
    return rest[1] === undefined ? null : moduleProblem(group.id, rest[1])
  }
  const group = GROUPS.find(g => groupLabel[g.id] === root)
  if (group) return moduleProblem(group.id, second)
  const mod = MODULES.find(m => moduleLabels(m).includes(root))
  if (mod.id === 'settings') {
    return leading(second, settingsTabs) && leading(second, settingsTabs) === bestLabel(second)
      ? null : `${second} is not a tab of Settings`
  }
  if (mod.id === 'account') {
    return leading(second, accountTabs) ? null : `${second} is not a tab of My Account`
  }
  const own = MODULES.find(m => m.id.toLowerCase() === second.toLowerCase() || leading(second, moduleLabels(m)))
  return own ? `${second} is a module of its own (${groupLabel[own.group] || 'no group'}), not a part of ${root}` : null
}

// Whichever of the tab and module labels the element starts with longest
function bestLabel(element) {
  return leading(element, [...settingsTabs, ...MODULES.flatMap(moduleLabels)])
}

function moduleProblem(groupId, element) {
  const inGroup = MODULES.filter(m => m.group === groupId)
  const mod = inGroup.find(m => leading(element, moduleLabels(m)))
  return mod ? null : `${element} is not a module of the ${groupLabel[groupId]} group`
}

const guides = fs.readdirSync(docsDir, { recursive: true }).filter(f => f.endsWith('.md')).sort()

describe('documented navigation paths', () => {
  it.each(guides)('%s names places the console has', (file) => {
    const found = pathsIn(fs.readFileSync(path.join(docsDir, file), 'utf8'))
    const bad = found.map(steps => [steps.join(' > '), problemsWith(steps)])
      .filter(([text, p]) => p && !ELSEWHERE.includes(text))
    expect(bad).toEqual([])
  })

  it('reads the registry: groups, modules and tabs', () => {
    expect(groupLabel.protocols).toBe('Protocols')
    expect(MODULES.find(m => m.id === 'est').group).toBe('protocols')
    expect(settingsTabs).toContain('Backup')
  })

  it('flags paths the console no longer has', () => {
    const bad = (text) => pathsIn(text).map(problemsWith).filter(Boolean)
    expect(bad('Go to **Operations > EST**')).toHaveLength(1)
    expect(bad('under **Operations → Discovery**:')).toHaveLength(1)
    expect(bad('(Settings → HSM):')).toHaveLength(1)
    expect(bad('**Settings** → **ACME** tab')).toHaveLength(1)
    expect(bad('Open Modules > Protocols > EST')).toEqual([])
    expect(bad('Open Modules > Administration > HSM Management')).toEqual([])
    expect(bad('Open Modules > Protocols > HSM')).toHaveLength(1)
    expect(bad('in Settings > Backup shows the space')).toEqual([])
    expect(bad('Settings > Audit Logs:')).toHaveLength(1)
    expect(bad('System > Updates shows the target')).toHaveLength(1)
    expect(bad('Dashboard → Create Certificate Authority')).toHaveLength(1)
  })
})

const userGuide = fs.readFileSync(path.join(docsDir, 'USER_GUIDE.md'), 'utf8')
const guidePaths = pathsIn(userGuide)

describe('user guide navigation', () => {
  it('writes its menu paths with ">" only', () => {
    expect(userGuide).not.toContain('\u2192')
  })

  it('gives menu paths, and every one resolves', () => {
    expect(guidePaths.length).toBeGreaterThanOrEqual(30)
    expect(guidePaths.map(steps => [steps.join(' > '), problemsWith(steps)]).filter(([, p]) => p)).toEqual([])
  })

  it.each(MODULES.filter(m => m.group))('names $id by its path in the Modules menu', (m) => {
    const label = lookup(m.labelKey)
    const hit = guidePaths.some(([root, g, page]) =>
      root === 'Modules' && g === groupLabel[m.group] && page && (page === label || page.startsWith(label + ' ')))
    expect(hit, `Modules > ${groupLabel[m.group]} > ${label}`).toBe(true)
  })

  it('names the account page, which sits outside the menu', () => {
    expect(userGuide).toContain(`**${lookup(MODULES.find(m => m.id === 'account').labelKey)}**`)
  })

  it('refuses a path the registry does not have', () => {
    const bad = (text) => pathsIn(text).map(problemsWith).filter(Boolean)
    expect(bad('Open **Modules** > **Protocols** > **Frobnicator**')).toHaveLength(1)
    expect(bad('Open **My Account** > **Billing**')).toHaveLength(1)
    expect(bad('Open **My Account** > **Security**')).toEqual([])
    expect(bad('Open **Modules** > **Governance** > **Key Recovery**')).toEqual([])
  })
})

// GitHub's heading slugs: lower case, markup and punctuation dropped, spaces to hyphens, repeats numbered
export function headingSlugs(markdown) {
  const seen = {}
  const out = new Set()
  for (const [, title] of markdown.replace(/^```.*?^```/gms, '').matchAll(/^#{1,6}\s+(.+?)\s*#*$/gm)) {
    const base = title.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1').replace(/[`*_]/g, '').toLowerCase()
      .replace(/[^\p{L}\p{N}\s-]/gu, '').trim().replace(/\s/g, '-')
    const n = seen[base] = (seen[base] ?? -1) + 1
    out.add(n ? `${base}-${n}` : base)
  }
  return out
}

export function brokenAnchors(file, markdown) {
  const prose = markdown.replace(/^```.*?^```/gms, '')
  const broken = []
  for (const [, target] of prose.matchAll(/\]\(([^)\s]*#[^)\s]*)(?:\s+"[^"]*")?\)/g)) {
    if (/^[a-z]+:/i.test(target)) continue
    const [rel, anchor] = target.split('#')
    const abs = rel ? path.resolve(path.dirname(path.join(docsDir, file)), rel) : path.join(docsDir, file)
    if (!abs.endsWith('.md') || !fs.existsSync(abs)) continue
    if (!anchor || !headingSlugs(fs.readFileSync(abs, 'utf8')).has(anchor)) broken.push(target)
  }
  return broken
}

describe('documented heading links', () => {
  it.each(guides)('%s links to headings that exist', (file) => {
    expect(brokenAnchors(file, fs.readFileSync(path.join(docsDir, file), 'utf8'))).toEqual([])
  })

  it('flags an anchor that no heading carries', () => {
    expect(brokenAnchors('USER_GUIDE.md', 'See [a](#getting-started) and [b](#nowhere).')).toEqual(['#nowhere'])
    expect(brokenAnchors('USER_GUIDE.md', 'See [a](HA.md#nowhere) and [b](HA.md#high-availability).')).toEqual(['HA.md#nowhere'])
    expect(headingSlugs('## A\n## A\n')).toEqual(new Set(['a', 'a-1']))
  })
})

describe('user guide claims about the bell and SCEP tabs', () => {
  const guide = fs.readFileSync(path.join(docsDir, 'USER_GUIDE.md'), 'utf8')

  it('does not list kinds the bell never requests', () => {
    const bell = guide.split('\n').find(l => l.startsWith('The bell lists'))
    expect(bell).toBeDefined()
    expect(bell).not.toMatch(/SCEP requests|key recoveries/)
  })

  it('places the SCEP challenge password on the Challenges tab, not Configuration', () => {
    const para = guide.split('\n').find(l => l.includes('The **Configuration** tab enables the server'))
    expect(para).toBeDefined()
    expect(para).not.toMatch(/holds the challenge password/)
    expect(para).toContain(`**${en.common.challenges}**`)
  })
})

// Every key string the console source names, and every namespace it reads with a template literal
function keysTheConsoleUses() {
  const srcDir = path.resolve(__dirname, '..')
  const files = fs.readdirSync(srcDir, { recursive: true })
    .filter(f => /\.jsx?$/.test(f) && !/(^|\/)(test|__tests__|i18n)\//.test(f))
  const keys = new Set()
  const prefixes = new Set()
  for (const f of files) {
    const code = fs.readFileSync(path.join(srcDir, f), 'utf8')
    for (const [, k] of code.matchAll(/['"`]([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)['"`]/g)) keys.add(k)
    for (const [, p] of code.matchAll(/`([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*\.)\$\{/g)) prefixes.add(p)
  }
  return { keys, prefixes }
}

function flatten(obj, prefix = '', out = {}) {
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === 'string') out[prefix + k] = v
    else if (v && typeof v === 'object') flatten(v, `${prefix}${k}.`, out)
  }
  return out
}

describe('user guide button names', () => {
  const { keys, prefixes } = keysTheConsoleUses()
  const shown = new Set(Object.entries(flatten(en))
    .filter(([k]) => keys.has(k) || [...prefixes].some(p => k.startsWith(p)))
    .map(([, v]) => v))
  // The Certificates page shortens its issue button to the first word of the label
  shown.add(en.certificates.issueCertificate.split(' ')[0])
  // Bold text that emphasises a concept rather than naming something on screen
  const EMPHASIS = ['list', 'details', 'deleted from UCM']
  const prose = userGuide.replace(/^```.*?^```/gms, '')
  const section = (title) => {
    const at = prose.indexOf(`\n### ${title}\n`)
    expect(at, title).toBeGreaterThanOrEqual(0)
    const rest = prose.slice(at + 5 + title.length)
    return rest.slice(0, rest.search(/\n#{2,3} |$/))
  }

  it('bolds only labels the console shows', () => {
    const bold = [...prose.matchAll(/\*\*([^*\n]+)\*\*/g)].map(m => m[1])
      .filter(b => !b.endsWith('.') && !EMPHASIS.includes(b))
    expect(bold.filter(b => !shown.has(b))).toEqual([])
  })

  it.each([
    ['Certificates', [en.certificates.issueCertificate.split(' ')[0]]],
    ['Certificate Authorities', [en.common.create, en.common.import]],
    ['Taking a CA Offline', [en.cas.takeOffline, en.cas.offlinePasswordProtected, en.cas.offlineFileExported]],
    ['Restoring an Offline CA', [en.cas.restore]],
    ['Certificate Signing Requests', [en.csrs.generateCSR, en.common.import, en.csrs.uploadCSR]],
    ['Templates', [en.templates.new, en.common.copy]],
    ['Trust Store', [en.trustStore.sync]],
    ['HSM Management', [en.hsm.newProvider, en.common.test]],
    ['Adding WebAuthn Key', [en.account.addKey]],
  ])('%s names the buttons of its page', (title, labels) => {
    const text = section(title)
    for (const label of labels) expect(text, label).toContain(`**${label}**`)
  })

  it.each([
    ['Certificate Authorities', [en.importExport.importCA]],
    ['HSM Management', [en.common.addDnsProvider, 'Test Connection']],
  ])('%s does not name buttons of another page', (title, labels) => {
    const text = section(title)
    for (const label of labels) expect(text, label).not.toContain(`**${label}**`)
  })
})
