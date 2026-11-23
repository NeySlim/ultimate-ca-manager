/** The issue form's drafts follow the session's: a sign-out, or another account signing in, drops them. */
import { describe, it, expect, beforeEach } from 'vitest'
import { clearDrafts, hasDraft, keepDraft, takeDraft } from '../issue/issueDrafts'
import { setDraftOwner, signOutDrafts } from '../../../lib/draftMemory'

beforeEach(() => { signOutDrafts(); clearDrafts() })

describe('issue drafts', () => {
  it('are kept for the account that wrote them', () => {
    setDraftOwner('alice')
    keepDraft('issue', { cn: 'www.example.com', password: 'never kept' })
    setDraftOwner('alice')
    expect(hasDraft('issue')).toBe(true)
    expect(takeDraft('issue')).toEqual({ cn: 'www.example.com' })
    expect(takeDraft('issue')).toBeNull()
  })

  it('go with a sign-out', () => {
    setDraftOwner('alice')
    keepDraft('issue', { cn: 'www.example.com' })
    keepDraft('renew:7', { cn: 'old.example.com' })
    signOutDrafts()
    expect(hasDraft('issue')).toBe(false)
    expect(takeDraft('renew:7')).toBeNull()
  })

  it('never reach another account signing in the same tab', () => {
    setDraftOwner('alice')
    keepDraft('issue', { cn: 'www.example.com' })
    setDraftOwner('bob')
    expect(takeDraft('issue')).toBeNull()
  })
})
