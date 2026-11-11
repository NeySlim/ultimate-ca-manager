/**
 * English help must not describe the pre-3.0 interface (widget dashboard,
 * floating CA/certificate detail, sidebar status). Terms are listed explicitly.
 */
import { describe, it, expect } from 'vitest'
import { helpGuides } from '../helpGuides'
import { helpContent } from '../helpContent'

// Per-entry exceptions: the Operations and ACME pages keep a sidebar tab layout; the e-mail template editor is still a floating window
const ALLOWED = {
  'guide settings': [/in a floating window/g],
  'content operations': [/Sidebar Tabs/g],
  'content acme': [/"Let's Encrypt orders" sidebar tab/g],
}
const RETIRED = [
  /widget/i, /edit layout/i, /\bcustomize\b.*sliders/i, /sidebar/i, /floating window/i,
  /green dot/i, /System Health panel/i, /certificate and CA detail panels/i,
  /the dashboard (shows|queue)/i, /updates in real-time via websocket/i,
]

function strings(node, out = []) {
  if (typeof node === 'string') out.push(node)
  else if (Array.isArray(node)) node.forEach((n) => strings(n, out))
  else if (node && typeof node === 'object' && Object.getPrototypeOf(node) === Object.prototype) {
    Object.entries(node).forEach(([k, v]) => { if (k !== 'icon') strings(v, out) })
  }
  return out
}

const entries = [
  ...Object.entries(helpGuides).map(([k, v]) => [`guide ${k}`, v]),
  ...Object.entries(helpContent).map(([k, v]) => [`content ${k}`, v]),
]

// The SSH CAs and CRL & OCSP pages keep their own CA panel, outside the inspector
const INSPECTOR_ONLY = /CA'?s? detail panels?/i

describe('English help vs the 3.0 interface', () => {
  it.each(entries)('%s has no retired interface term', (_name, entry) => {
    let text = strings(entry).join('\n')
    ;(ALLOWED[_name] || []).forEach((re) => { text = text.replace(re, '') })
    const hits = RETIRED.filter((re) => re.test(text)).map(String)
    if (!/(sshCas|crlocsp)$/.test(_name) && INSPECTOR_ONLY.test(text)) hits.push(String(INSPECTOR_ONLY))
    expect(hits).toEqual([])
  })

  it('crlocsp points to the page CA panel, not the inspector', () => {
    const text = [...strings(helpGuides.crlocsp), ...strings(helpContent.crlocsp)].join('\n')
    expect(text).not.toMatch(/CA in the inspector/i)
  })

  it('no entry still labels the overview "Dashboard"', () => {
    const related = Object.values(helpContent).flatMap((e) => e.related || [])
    expect(related).not.toContain('Dashboard')
    expect(helpGuides.dashboard.title).toBe('Overview')
  })
})
