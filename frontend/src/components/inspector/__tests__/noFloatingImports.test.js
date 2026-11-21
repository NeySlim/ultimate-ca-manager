/**
 * The pre-Atelier interface and the shell's inspector are gone: their files must not
 * exist and nothing may import them. The floating windows went last (help, email template).
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = join(__dirname, '../../..')
const LEGACY = {
  'components/FloatingDetailWindow.jsx': /\bFloatingDetailWindow\b/,
  'components/DetailWindowLayer.jsx': /\bDetailWindowLayer\b/,
  'contexts/WindowManagerContext.jsx': /\bWindowManagerContext\b|\buseWindowManager\b|\bWindowManagerProvider\b/,
  'components/Sidebar.jsx': /\/Sidebar['"]/,
  'components/DashboardChart.jsx': /\bDashboardChart\b/,
  'pages/DashboardPage.jsx': /\bDashboardPage\b/,
  // The shell's inspector: every object now opens in the dock its zone draws
  'components/inspector/InspectorDock.jsx': /\bInspectorDock\b/,
  'components/inspector/InspectorObject.jsx': /\bInspectorObject\b/,
  'components/inspector/InspectorTabs.jsx': /\/InspectorTabs['"]/,
  'components/inspector/config.js': /\/inspector\/config['"]/,
  'components/inspector/placement.js': /\/inspector\/placement['"]/,
  'components/inspector/certificate/CertificateDetail.jsx': /\/inspector\/certificate\//,
  'components/detail/CertificatePanel.jsx': /\/detail\/|\bCertificatePanel\b|\bTrustCertPanel\b/,
  // The old shell's floating windows: the help and the email template editor are the mockup's dialogs
  'components/ui/FloatingWindow.jsx': /\bFloatingWindow\b|\/FloatingWindow['"]/,
  'hooks/useFloatingWindow.js': /\buseFloatingWindow\b/,
  'components/ui/FloatingHelpPanel.jsx': /\bFloatingHelpPanel\b/,
  'components/EmailTemplateWindow.jsx': /\bEmailTemplateWindow\b/,
}

function sources(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) { if (name !== '__tests__' && name !== 'node_modules') sources(p, out) }
    else if (/\.(jsx?|tsx?)$/.test(name) && !/\.test\./.test(name)) out.push(p)
  }
  return out
}

// Whole import/export-from statements and dynamic imports, however many lines they span
export function importStatements(text) {
  return text.match(/\b(?:import|export)\b[^;'"`]*?\bfrom\s*['"][^'"]+['"]|\bimport\s*\(?\s*['"][^'"]+['"]/g) || []
}

describe('import statement scanner', () => {
  it('sees a multi-line import and a dynamic one, not a bare mention', () => {
    const text = "import {\n  useWindowManager,\n} from '../contexts'\nconst x = import('./Foo')\n// useWindowManager"
    const found = importStatements(text)
    expect(found).toHaveLength(2)
    expect(LEGACY['contexts/WindowManagerContext.jsx'].test(found[0])).toBe(true)
  })
})

// Live = reached from the entry point through relative imports (barrels included),
// never through a legacy module
export function liveModules(files, legacy, entry = 'main.jsx') {
  const byPath = new Map(files.map(([rel, text]) => [rel, text]))
  const resolve = (fromRel, spec) => {
    const base = join(dirname(fromRel), spec).split('\\').join('/')
    return ['', '.js', '.jsx', '/index.js', '/index.jsx'].map((x) => base + x).find((c) => byPath.has(c))
  }
  const live = new Set()
  const queue = [entry]
  while (queue.length) {
    const rel = queue.pop()
    if (live.has(rel) || legacy.includes(rel)) continue
    live.add(rel)
    for (const st of importStatements(byPath.get(rel))) {
      const spec = st.match(/['"]([^'"]+)['"]$/)?.[1]
      const target = spec?.startsWith('.') && resolve(rel, spec)
      if (target) queue.push(target)
    }
  }
  return live
}

describe('live module walk', () => {
  const graph = [
    ['main.jsx', "import A from './a'\nimport L from './legacy'"],
    ['a.jsx', 'export default 1'],
    ['legacy.jsx', "import O from './onlyLegacy'"],
    ['onlyLegacy.jsx', 'export default 2'],
    ['orphan.jsx', 'export default 3'],
  ]
  it('keeps what the entry reaches, drops orphans and what only a legacy module imports', () => {
    const live = liveModules(graph, ['legacy.jsx'])
    expect([...live].sort()).toEqual(['a.jsx', 'main.jsx'])
  })
})

describe('legacy interface', () => {
  const files = sources(SRC).map((p) => [relative(SRC, p), readFileSync(p, 'utf8')])

  it.each(Object.keys(LEGACY))('%s no longer exists', (legacy) => {
    expect(existsSync(join(SRC, legacy))).toBe(false)
  })

  it.each(Object.entries(LEGACY))('%s is imported by nothing', (legacy, pattern) => {
    const users = files
      .filter(([, text]) => importStatements(text).some((st) => pattern.test(st)))
      .map(([rel]) => rel)
    expect(users).toEqual([])
  })
})
