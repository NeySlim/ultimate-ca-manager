/**
 * Every "A > B" path the guides give names a place the console has: a group and a module of
 * the Modules menu (read from the navigation registry), or a tab of the Settings page, and every
 * step after the module is a label its page shows. The user guide must also name every page of
 * the menu by its full path, and links to guide headings must land on a heading that exists.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { GROUPS, MODULES } from '../navigation/registry'
import en from '../i18n/locales/en.json'
import { BELL_KINDS, FAILURE_ACTIONS, SESSION_ACTIONS } from '../components/shell/notifications'

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

// Labels a page shows (tabs, sections, buttons): the en.json values of the keys its source names.
// A module's page is its file plus the folder of the same name, and everything below that.
const PAGES_DIR = path.resolve(__dirname, '../pages')
const pagesJs = fs.readFileSync(path.resolve(__dirname, '../navigation/pages.js'), 'utf8')
const PAGE_FILE = Object.fromEntries([...pagesJs.matchAll(/^\s+['"]?([\w-]+)['"]?: lazyWithRetry\(\(\) => import\('\.\.\/pages\/(\w+)'\)/gm)].map(m => [m[1], m[2]]))
const PAGE_DIR = { users: 'users', acme: 'acme', scep: 'scep', cas: 'cas', certificates: 'certificates', discovery: 'discovery', settings: 'settings', audit: 'activity' }
const sourcesOf = (dir) => fs.existsSync(dir)
  ? fs.readdirSync(dir, { recursive: true }).filter(f => /\.jsx?$/.test(f) && !/(^|\/)__tests__\//.test(f)).map(f => path.join(dir, f))
  : []
function labelsOf(mod) {
  const files = [path.join(PAGES_DIR, PAGE_FILE[mod.id] + '.jsx'), ...sourcesOf(path.join(PAGES_DIR, PAGE_DIR[mod.id] || '-'))]
    .filter(f => fs.existsSync(f))
  const flat = flatten(en)
  const out = new Set()
  for (const f of files) {
    const code = fs.readFileSync(f, 'utf8')
    for (const [, k] of code.matchAll(/['"`]([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)['"`]/g)) if (flat[k]) out.add(flat[k])
    for (const [, p] of code.matchAll(/`([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*\.)\$\{/g)) {
      for (const [k, v] of Object.entries(flat)) if (k.startsWith(p)) out.add(v)
    }
  }
  // A label with a trailing "(CA)" is written without it in prose
  for (const l of [...out]) out.add(l.replace(/\s*\([^)]*\)$/, ''))
  // The Certificates page shortens its issue button to the first word of the label
  if (mod.id === 'certificates') out.add(en.certificates.issueCertificate.split(' ')[0])
  return [...out]
}
const labelCache = {}
const pageLabels = (mod) => (labelCache[mod.id] ??= labelsOf(mod))

// Roots the earlier console had and this one has not: a path under one of them is always stale
const GONE = ['System', 'Admin', 'Dashboard']
const ROOTS = ['Modules', ...GONE, ...Object.values(groupLabel), ...MODULES.flatMap(moduleLabels), ...settingsTabs]
  .filter((r, i, all) => all.indexOf(r) === i)
  .sort((a, b) => b.length - a.length)
const ROOT_RE = new RegExp(`(?:^|[^\\w])(${ROOTS.map(r => r.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')).join('|')})((?:\\s*(?:>|→)\\s*[A-Z][^>→()\`*,.;:|\\n]*)+)`, 'g')

// Paths of another product's console, quoted by an integration guide
const ELSEWHERE = ['Templates > SCEP certificate', 'Settings > General > VPN & Device Management']

export function pathsIn(markdown) {
  // A path wrapped onto a lowercase continuation line is one path
  const prose = markdown.replace(/^```.*?^```/gms, '').replace(/\*\*|`/g, '').replace(/(\S)[ \t]*\n[ \t]*(?=[a-z])/g, '$1 ')
  return [...prose.matchAll(ROOT_RE)].map(m => [m[1], ...m[2].split(/\s*(?:>|→)\s*/).filter(Boolean).map(s => s.trim())])
}

export function problemsWith(steps) {
  const [root, ...rest] = steps
  const second = rest[0]
  if (GONE.includes(root)) return `${root} is not a place of this console`
  let mod
  let tail
  if (root === 'Modules') {
    const group = GROUPS.find(g => groupLabel[g.id] === second)
    if (!group) return `${second} is not a group of the Modules menu`
    if (rest[1] === undefined) return null
    mod = moduleIn(group.id, rest[1])
    if (!mod) return `${rest[1]} is not a module of the ${groupLabel[group.id]} group`
    tail = rest.slice(2)
  } else {
    const group = GROUPS.find(g => groupLabel[g.id] === root)
    if (group) {
      mod = moduleIn(group.id, second)
      if (!mod) return `${second} is not a module of the ${groupLabel[group.id]} group`
      tail = rest.slice(1)
    } else {
      mod = MODULES.find(m => moduleLabels(m).includes(root))
      if (!mod) return `${root} is a tab of Settings, not a place of its own`
      tail = rest
    }
  }
  if (mod.id === 'settings' && tail.length) {
    const tab = tail[0]
    if (!(leading(tab, settingsTabs) && leading(tab, settingsTabs) === bestLabel(tab))) return `${tab} is not a tab of Settings`
  } else if (mod.id === 'account' && tail.length) {
    if (!leading(tail[0], accountTabs)) return `${tail[0]} is not a tab of My Account`
  } else if (tail.length) {
    const own = MODULES.find(m => m.id.toLowerCase() === tail[0].toLowerCase() || leading(tail[0], moduleLabels(m)))
    if (own && own !== mod) {
      return `${tail[0]} is a module of its own (${groupLabel[own.group] || 'no group'}), not a part of ${root}`
    }
  }
  const labels = pageLabels(mod)
  // Only the last step may carry trailing prose: every step before it is a label, exactly
  const unknown = tail.slice(mod.id === 'settings' || mod.id === 'account' ? 1 : 0)
    .find((step, i, steps) => (i < steps.length - 1 ? !labels.includes(step) : !leading(step, labels)))
  return unknown ? `${unknown} is not a tab, section or button of ${lookup(mod.labelKey)}` : null
}

// Whichever of the tab and module labels the element starts with longest
function bestLabel(element) {
  return leading(element, [...settingsTabs, ...MODULES.flatMap(moduleLabels)])
}

function moduleIn(groupId, element) {
  return MODULES.filter(m => m.group === groupId).find(m => leading(element, moduleLabels(m)))
}

const repoDir = path.resolve(docsDir, '..')
const markdownUnder = (dir) => fs.readdirSync(path.join(repoDir, dir), { recursive: true })
  .filter(f => f.endsWith('.md')).map(f => path.join(dir, f))
// Rewritten by another change: its stale path (Settings > ACME client) is left to it, not read here
const REWRITTEN_ELSEWHERE = ['README.md']
const guides = [...markdownUnder('docs'), ...markdownUnder('examples'),
  'UPGRADE.md', 'README.md', 'RELEASE_TESTING.md']
  .filter(f => !REWRITTEN_ELSEWHERE.includes(f)).sort()

describe('documented navigation paths', () => {
  it('reads the guides at the root and the examples too', () => {
    expect(guides).toEqual(expect.arrayContaining(['UPGRADE.md', path.join('docs', 'ADMIN_GUIDE.md')]))
    expect(guides.some(f => f.startsWith('examples'))).toBe(true)
  })

  it.each(guides)('%s names places the console has', (file) => {
    const found = pathsIn(fs.readFileSync(path.join(repoDir, file), 'utf8'))
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
    expect(bad('Open Certificates > Frobnicate')).toHaveLength(1)
    expect(bad('Open Certificate Tools > Bogus Tool')).toHaveLength(1)
    expect(bad('Open Settings > About > Check Nonsense')).toHaveLength(1)
    expect(bad('Open Modules > PKI > Certificates > Bogus')).toHaveLength(1)
    expect(bad('Open Windows Autoenrollment > Bogus')).toHaveLength(1)
    expect(bad('Open Settings > Windows Autoenrollment > Add profile')).toEqual([])
    expect(bad('Open ACME > Let\'s Encrypt > Certificate Authorities')).toEqual([])
    expect(bad('Open Modules > PKI > Certificates > Issue Certificate')).toEqual([])
    // A step before the last is a label exactly; the last one may be followed by prose
    expect(bad('Open Modules > PKI > Certificates > Issue Bogus > Export')).toHaveLength(1)
    expect(bad('Open Modules > PKI > Certificates > Issue > Bogus')[0]).toMatch(/^Bogus is not/)
    expect(bad('Open Modules > PKI > Certificates > Export shows the formats')).toEqual([])
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
// Heading text without its markup: emphasis markers go, literal underscores (also in code) stay
function plainTitle(title) {
  return title.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1').split(/(`[^`]*`)/)
    .map((part, i) => i % 2 ? part.slice(1, -1)
      : part.replace(/\*/g, '').replace(/(^|[^\w])_+(?=\S)(.+?)_+(?=[^\w]|$)/g, '$1$2'))
    .join('')
}

export function headingSlugs(markdown) {
  const seen = {}
  const out = new Set()
  for (const [, title] of markdown.replace(/^```.*?^```/gms, '').matchAll(/^#{1,6}\s+(.+?)\s*#*$/gm)) {
    const base = plainTitle(title).toLowerCase()
      .replace(/[^\p{L}\p{N}\s_-]/gu, '').trim().replace(/\s/g, '-')
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
    if (!abs.endsWith('.md')) continue
    if (!fs.existsSync(abs) || !anchor || !headingSlugs(fs.readFileSync(abs, 'utf8')).has(anchor)) broken.push(target)
  }
  return broken
}

describe('documented heading links', () => {
  it.each(guides)('%s links to headings that exist', (file) => {
    // brokenAnchors resolves from docs/: a guide of the root or of examples/ is given relative to it
    expect(brokenAnchors(path.relative('docs', file), fs.readFileSync(path.join(repoDir, file), 'utf8'))).toEqual([])
  })

  it('flags an anchor that no heading carries', () => {
    expect(brokenAnchors('USER_GUIDE.md', 'See [a](#getting-started) and [b](#nowhere).')).toEqual(['#nowhere'])
    expect(brokenAnchors('USER_GUIDE.md', 'See [a](HA.md#nowhere) and [b](HA.md#high-availability).')).toEqual(['HA.md#nowhere'])
    expect(brokenAnchors('USER_GUIDE.md', 'See [a](NO_SUCH_GUIDE.md#intro).')).toEqual(['NO_SUCH_GUIDE.md#intro'])
    expect(headingSlugs('## A\n## A\n')).toEqual(new Set(['a', 'a-1']))
  })

  it('keeps literal underscores in a slug and drops emphasis markers', () => {
    const slugs = headingSlugs('#### Reverse proxy & trusted_proxies (since v2.142)\n## `my_code` and _em_ **bold**\n')
    expect(slugs).toEqual(new Set(['reverse-proxy--trusted_proxies-since-v2142', 'my_code-and-em-bold']))
    const link = (anchor) => brokenAnchors('USER_GUIDE.md', `[a](ADMIN_GUIDE.md#${anchor})`)
    expect(link('reverse-proxy--trusted_proxies-since-v2142')).toEqual([])
    expect(link('reverse-proxy--trustedproxies-since-v2142')).toHaveLength(1)
  })
})

describe('user guide claims about the bell and SCEP tabs', () => {
  const guide = fs.readFileSync(path.join(docsDir, 'USER_GUIDE.md'), 'utf8')

  it('does not list kinds the bell never requests', () => {
    const bell = guide.split('\n').find(l => l.startsWith('The bell lists'))
    expect(bell).toBeDefined()
    expect(bell).not.toMatch(/SCEP requests|key recoveries/)
  })

  it('names every kind the bell can show by the label the console gives it', () => {
    const bell = guide.split('\n').find(l => l.startsWith('The bell lists'))
    for (const kind of [...BELL_KINDS, ...FAILURE_ACTIONS, ...SESSION_ACTIONS]) {
      const label = en.shell.bell.kinds[kind]
      expect(label, kind).toBeTruthy()
      expect(bell.toLowerCase(), label).toContain(label.toLowerCase())
    }
  })

  it('says where a bell entry leads', () => {
    const bell = guide.split('\n').find(l => l.startsWith('The bell lists'))
    expect(bell).not.toContain('opens the page of the item')
    expect(bell).toMatch(/audit entries open the audit log/i)
    expect(bell).toMatch(/queue entry without a path has no link/i)
  })

  it('says the Modules menu lists modules, and what refuses a renewal', () => {
    expect(guide).not.toContain('lists every page you may open')
    expect(guide).toContain('lists every module you may open')
    const renewing = guide.split('\n').find(l => l.startsWith('**Renewing.**'))
    expect(renewing).toMatch(/private key the server does not hold/)
  })

  it('gives the Viewer role everything the permission table gives it', () => {
    const row = guide.split('\n').find(l => l.startsWith('| **Viewer** |'))
    for (const word of ['CSRs', 'trust store', 'SSH']) expect(row, word).toContain(word)
  })

  it('places the SCEP challenge password in the Challenges of the authorities view, not Configuration', () => {
    const para = guide.split('\n').find(l => l.includes('which enables the server and chooses the CA'))
    expect(para).toBeDefined()
    expect(para).not.toMatch(/Configuration\*\*[^.]*challenge password/)
    expect(para).toContain(`**${en.scep.views.challenges}**`)
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
    ['Certificates', [en.certificates.issueCertificate.split(' ')[0], en.common.revoke, en.certificates.removeHold]],
    ['Certificate Authorities', [en.common.create, en.common.import]],
    ['Taking a CA Offline', [en.cas.takeOffline, en.cas.offlinePasswordProtected, en.cas.offlineFileExported]],
    ['Restoring an Offline CA', [en.cas.restore]],
    ['Certificate Signing Requests', [en.csrs.generateCSR, en.common.import, en.csrs.uploadCSR, en.csrs.sign, en.common.signCSR, en.csrs.signAgain]],
    ['Templates', [en.templates.new, en.common.copy]],
    ['Trust Store', [en.trustStore.sync, en.common.export, en.trustStore.exportBundle]],
    ['Users', [en.users.createUser]],
    ['Audit Logs', [en.audit.verifyIntegrity]],
    ['Settings', [en.scheduler.runNow]],
    ['Enabling 2FA (TOTP)', [en.common.enable2FA]],
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
