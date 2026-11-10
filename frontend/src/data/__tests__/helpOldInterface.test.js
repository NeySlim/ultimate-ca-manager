/**
 * English help must not describe the pre-3.0 interface (widget dashboard,
 * floating CA/certificate detail, sidebar status). Terms are listed explicitly.
 */
import { describe, it, expect } from 'vitest'
import { helpGuides } from '../helpGuides'
import { helpContent } from '../helpContent'

// Sidebar tab layout still exists on the Operations and ACME pages; the e-mail template editor is still a floating window
const ALLOWED = [/Sidebar Tabs/g, /"Let's Encrypt orders" sidebar tab/g, /in a floating window/g]
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

// The SSH CAs page keeps its own detail panel, outside the inspector
const INSPECTOR_ONLY = /CA'?s? detail panels?/i

describe('English help vs the 3.0 interface', () => {
  it.each(entries)('%s has no retired interface term', (_name, entry) => {
    let text = strings(entry).join('\n')
    ALLOWED.forEach((re) => { text = text.replace(re, '') })
    const hits = RETIRED.filter((re) => re.test(text)).map(String)
    if (!/sshCas$/.test(_name) && INSPECTOR_ONLY.test(text)) hits.push(String(INSPECTOR_ONLY))
    expect(hits).toEqual([])
  })

  it('no entry still labels the overview "Dashboard"', () => {
    const related = Object.values(helpContent).flatMap((e) => e.related || [])
    expect(related).not.toContain('Dashboard')
    expect(helpGuides.dashboard.title).toBe('Overview')
  })
})
