/**
 * AppShell Smoke Tests — catches undefined icons, missing imports, render crashes
 * This test specifically prevents React Error #130 (undefined component type)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Verify all Phosphor icon imports resolve to real components
describe('AppShell — icon imports', () => {
  // The dynamic import pulls in the entire @phosphor-icons/react package;
  // on a cold module cache that alone can exceed the default 5s timeout.
  it('all navigation icons are valid React components', { timeout: 30000 }, async () => {
    // Import the actual module to check real exports
    const phosphor = await import('@phosphor-icons/react')
    
    // These are ALL icons used in AppShell navigation
    const requiredIcons = [
      'House', 'CertificateIcon', 'ShieldCheck', 'FileText',
      'Notebook', 'Vault', 'Globe', 'ArrowsClockwise',
      'Gear', 'User', 'UsersThree', 'ClipboardText',
      'Gavel', 'Stamp', 'ChartBar',
    ]

    // CertificateIcon is aliased from Certificate in AppShell
    const iconMap = {
      ...phosphor,
      CertificateIcon: phosphor.Certificate,
    }

    for (const iconName of requiredIcons) {
      const icon = iconMap[iconName]
      expect(icon, `Icon '${iconName}' should be exported from @phosphor-icons/react`).toBeDefined()
      expect(typeof icon === 'function' || typeof icon === 'object',
        `Icon '${iconName}' should be a valid React component`).toBe(true)
    }
  })

  it('no navigation item has undefined icon', async () => {
    // Dynamically import AppShell and extract nav items
    // We test via the icon import validation above, but also parse the source
    const fs = await import('fs')
    const path = await import('path')
    const source = fs.readFileSync(
      path.resolve(__dirname, '../AppShell.jsx'), 'utf8'
    )
    
    // Check that no nav item has undefined icon value or missing icon property
    const iconUndefinedPattern = /icon:\s*undefined/g
    const matches = source.match(iconUndefinedPattern)
    expect(matches, 'No nav item should have an undefined icon').toBeNull()
  })
})

/**
 * The list above is hand-maintained and has drifted from the components: it
 * names icons the shell no longer uses (Notebook, UsersThree, ClipboardText)
 * while missing ones it does (Broadcast, Terminal, Clock). A stale list still
 * passes, so it cannot catch the failure it exists for — a nav entry pointing
 * at an icon that resolves to undefined, which React reports as Error #130 at
 * render time.
 *
 * These tests derive the icons from the source instead, so adding a nav item
 * with a bad icon fails here rather than in the browser.
 */
describe('AppShell — icons derived from source', () => {
  // The nav icons are declared by the registry, the shell components only import theirs
  const COMPONENTS = [
    '../shell/TopBar.jsx', '../shell/ModulesMenu.jsx', '../shell/UserMenu.jsx',
    '../../navigation/registry.js',
  ]
  const NAV_ICON_SOURCES = ['../../navigation/registry.js']

  async function readSource(relPath) {
    const fs = await import('fs')
    const path = await import('path')
    return fs.readFileSync(path.resolve(__dirname, relPath), 'utf8')
  }

  /** Parse the `@phosphor-icons/react` import block into {imported, local} pairs. */
  function parsePhosphorImports(source) {
    // `[^}]*` keeps the match anchored to this import's own specifier list —
    // a lazy `[\s\S]*?` would start at an earlier `import {` and swallow it.
    const block = source.match(
      /import\s*\{([^}]*)\}\s*from\s*['"]@phosphor-icons\/react['"]/
    )
    if (!block) return []
    return block[1]
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((spec) => {
        const aliased = spec.match(/^(\S+)\s+as\s+(\S+)$/)
        return aliased
          ? { imported: aliased[1], local: aliased[2] }
          : { imported: spec, local: spec }
      })
  }

  it.each(COMPONENTS)(
    'every phosphor icon %s imports is a real export',
    { timeout: 30000 },
    async (relPath) => {
      const phosphor = await import('@phosphor-icons/react')
      const specs = parsePhosphorImports(await readSource(relPath))

      expect(specs.length, `${relPath} should import icons from phosphor`).toBeGreaterThan(0)
      for (const { imported } of specs) {
        const icon = phosphor[imported]
        expect(icon, `'${imported}' is imported by ${relPath} but not exported by @phosphor-icons/react`).toBeDefined()
        expect(
          typeof icon === 'function' || typeof icon === 'object',
          `'${imported}' is not a valid React component`
        ).toBe(true)
      }
    }
  )

  it.each(NAV_ICON_SOURCES)(
    'every `icon:` in %s refers to something that is in scope',
    async (relPath) => {
      const source = await readSource(relPath)
      const inScope = new Set(parsePhosphorImports(source).map((s) => s.local))

      // Identifiers used as nav-item icons, e.g. `icon: ShieldCheck,`
      const used = [...source.matchAll(/icon:\s*([A-Za-z_$][\w$]*)/g)].map((m) => m[1])

      expect(used.length, `${relPath} should declare nav icons`).toBeGreaterThan(0)
      for (const name of used) {
        expect(
          inScope.has(name),
          `${relPath} uses \`icon: ${name}\` but never imports ${name} — it resolves to undefined and React throws Error #130`
        ).toBe(true)
      }
    }
  )
})
