/**
 * What the certificate detail works out from the record: the chain root first, the
 * share of validity left, the history merged with the audit log, the ACME failure matched
 * on the names.
 */
import { describe, expect, it } from 'vitest'
import { chainPath, chainSentence } from '../chainPath'
import { alternativeNames, validityFacts } from '../certificateFacts'
import { recordEvents, mergeHistory, fromAudit } from '../historyEvents'
import { matchFailure } from '../useLastFailure'

const t = (key, opts) => (typeof opts === 'string' ? opts : opts?.count !== undefined ? `${key}:${opts.count}` : opts?.anchor !== undefined ? `${key}:${opts.anchor}` : key)

describe('chainPath', () => {
  const cert = {
    subject: 'CN=web.example.com', issuer: 'CN=Issuing CA', caref: 'ca-2',
    chain_status: {
      status: 'complete', trust_source: 'managed_ca', trust_anchor: 'Root CA',
      chain: [{ name: 'Issuing CA', type: 'managed_ca' }, { name: 'Root CA', type: 'managed_ca', cross_certificate_id: 4 }],
    },
  }

  it('puts the root first and marks the issuing authority, the server listing it first', () => {
    const { path, status, anchor } = chainPath(cert)
    expect(path.map((n) => n.name)).toEqual(['Root CA', 'Issuing CA'])
    expect(path[0]).toMatchObject({ root: true, level: 1, issuing: false, cross: true, kind: 'managed' })
    expect(path[1]).toMatchObject({ root: false, level: 2, issuing: true, cross: false })
    expect(status).toBe('complete')
    expect(anchor).toBe('Root CA')
  })

  it('names no root while the chain is not verified up to one', () => {
    const { path } = chainPath({ ...cert, chain_status: { ...cert.chain_status, status: 'partial' } })
    expect(path.every((n) => !n.root && n.level === null)).toBe(true)
  })

  it('falls back on the issuer the certificate names, as one not held', () => {
    const { path, status } = chainPath({ subject: 'CN=a', issuer: 'CN=Outside CA,O=Other' })
    expect(path).toEqual([{ name: 'Outside CA', kind: 'unknown', issuing: false, cross: false, root: false, level: null }])
    expect(status).toBe('unknown')
  })

  it('draws nothing above a self-signed certificate', () => {
    const chain = chainPath({ subject: 'CN=a', issuer: 'CN=a' })
    expect(chain.path).toEqual([])
    expect(chainSentence(chain, t)).toEqual({ tone: 'muted', text: 'inspector.cert.selfSigned' })
  })

  it.each([
    ['complete', 'managed_ca', 'good', 'inspector.cert.chainToRoot:Root CA'],
    ['complete', 'trust_store', 'good', 'inspector.cert.chainToStore:Root CA'],
    ['partial', 'managed_ca', 'muted', 'inspector.cert.chainPartial'],
    ['incomplete', null, 'warn', 'details.chainIncompleteHint'],
  ])('says a %s chain anchored by %s in one sentence', (status, source, tone, text) => {
    const chain = chainPath({ ...cert, chain_status: { ...cert.chain_status, status, trust_source: source } })
    expect(chainSentence(chain, t)).toEqual({ tone, text })
  })

  it('says nothing of a chain the server did not judge', () => {
    expect(chainSentence(chainPath({ subject: 'CN=a', issuer: 'CN=b' }), t)).toBeNull()
  })
})

describe('certificate facts', () => {
  it('reads the alternative names from the extension, then from the combined column', () => {
    expect(alternativeNames({ extensions: { subject_alt_names: { entries: [{ type: 'DNS', value: 'a.example' }] } }, san_combined: 'x' }))
      .toEqual([{ type: 'DNS', value: 'a.example' }])
    expect(alternativeNames({ san_combined: 'a.example, b.example' })).toEqual([{ type: null, value: 'a.example' }, { type: null, value: 'b.example' }])
    expect(alternativeNames({})).toEqual([])
  })

  it('works out the share of the validity that is left', () => {
    const facts = validityFacts({ days_remaining: 25, valid_from: '2026-01-01T00:00:00Z', valid_to: '2026-04-11T00:00:00Z', status: 'expiring' })
    expect(facts).toMatchObject({ days: 25, state: 'expiring', tone: 'warn' })
    expect(Math.round(facts.share)).toBe(25)
  })

  it.each([
    [{ revoked: true, days_remaining: 90 }, 'revoked', ''],
    [{ days_remaining: -3 }, 'expired', 'bad'],
    [{ days_remaining: 0 }, 'expired', 'bad'],
    [{ days_remaining: 200, status: 'valid' }, 'valid', ''],
  ])('names the state of %j', (cert, state, tone) => {
    expect(validityFacts(cert)).toMatchObject({ state, tone })
  })
})

describe('history', () => {
  const cert = { created_at: '2026-01-01T10:00:00Z', created_by: 'admin', source: 'acme', renewed_at: '2026-03-01T10:00:00Z', renewed_times: 3 }

  it('keeps what the record says: issued, renewed, revoked with its reason', () => {
    const events = recordEvents({ ...cert, revoked: true, revoked_at: '2026-04-01T10:00:00Z', revoke_reason: 'keyCompromise' }, t)
    expect(events.map((e) => e.label)).toEqual(['inspector.history.issued', 'inspector.history.renewedTimes:3', 'inspector.history.revokedReason'])
    expect(events[0].actor).toBe('admin')
    expect(events[2].revoked).toBe(true)
  })

  it('says imported for a certificate that came from outside', () => {
    expect(recordEvents({ created_at: '2026-01-01T10:00:00Z', source: 'import' }, t)[0].label).toBe('inspector.history.imported')
  })

  it('counts an event once when the audit log has it too, newest first', () => {
    const audit = [
      fromAudit({ timestamp: '2026-01-01T10:00:04Z', username: 'admin', action: 'certificate_issued', success: true }),
      fromAudit({ timestamp: '2026-02-01T09:00:00Z', username: 'ops', action: 'certificate.export', success: false, details: 'refused' }),
    ]
    const merged = mergeHistory(recordEvents(cert, t), audit)
    expect(merged.map((e) => e.label)).toEqual(['inspector.history.renewedTimes:3', 'certificate export', 'certificate issued'])
    expect(merged[1]).toMatchObject({ failed: true, actor: 'ops', detail: 'refused' })
  })
})

describe('matchFailure', () => {
  const cert = { common_name: 'Web.Example.com', extensions: { subject_alt_names: { entries: [{ type: 'DNS', value: 'alt.example.com' }, { type: 'IP', value: '10.0.0.1' }] } } }
  const item = (over) => ({ kind: 'acme_order_failed', label: 'other.example.com', due_at: '2026-11-01T00:00:00Z', href_hint: '/acme?tab=history', ...over })

  it('keeps the newest failure naming the certificate, by its name or an alternative name', () => {
    const found = matchFailure([
      item({ label: 'web.example.com', due_at: '2026-11-01T00:00:00Z' }),
      item({ label: 'x.example.com, alt.example.com', due_at: '2026-11-05T00:00:00Z' }),
      item({}),
    ], cert, ['acme_order_failed'])
    expect(found).toEqual({ kind: 'acme_order_failed', label: 'x.example.com, alt.example.com', at: '2026-11-05T00:00:00Z', href: '/acme?tab=history' })
  })

  it('finds none for other names, other kinds or an empty queue', () => {
    expect(matchFailure([item({})], cert, ['acme_order_failed'])).toBeNull()
    expect(matchFailure([item({ label: 'web.example.com', kind: 'cert_expiring' })], cert, ['acme_order_failed'])).toBeNull()
    expect(matchFailure(undefined, cert, ['acme_order_failed'])).toBeNull()
  })

  it('follows no link that leaves the application', () => {
    expect(matchFailure([item({ label: 'web.example.com', href_hint: 'https://elsewhere.example' })], cert, ['acme_order_failed']).href).toBeNull()
  })
})
