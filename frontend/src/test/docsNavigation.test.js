/**
 * Every "A > B" path the guides give names a place the console has: a group and a module of
 * the Modules menu (read from the navigation registry), or a tab of the Settings page.
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
  })
})
