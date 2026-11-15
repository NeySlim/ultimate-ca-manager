import { describe, it, expect } from 'vitest'
import { queueItems } from '../notifications'

const item = (tier, id) => ({ kind: 'truststore_expiring', tier, id, label: 'Root', due_at: '2026-01-01T00:00:00Z', href_hint: `/truststore/${id}` })

describe('trust store anchors in the bell', () => {
  it('an expired anchor (critical) is announced and links to the anchor, one expiring later (warning) is not', () => {
    const items = queueItems({ items: [item('critical', 4), item('warning', 5)] })
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({ kind: 'truststore_expiring', href: '/truststore/4', title: 'Root' })
  })
})
