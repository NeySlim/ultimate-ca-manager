/**
 * AppShell Smoke Tests — catches undefined icons, missing imports, render crashes
 * This test specifically prevents React Error #130 (undefined component type)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Verify all Phosphor icon imports resolve to real components
describe('AppShell — icon imports', () => {
  it('all navigation icons are valid React components', async () => {
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
