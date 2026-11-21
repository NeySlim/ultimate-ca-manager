/**
 * A taken unique subject (409 naming the override field) is asked again with the override
 * once the operator confirms; any other error, or a refusal, changes nothing.
 */
import { describe, it, expect, vi } from 'vitest'
import { issueWithSubjectOverride, takenSubject } from '../uniqueSubject'

const t = (key, opts) => (opts ? `${key}:${JSON.stringify(opts)}` : key)
const taken = Object.assign(new Error('taken'), {
  status: 409,
  data: { details: { subject: 'CN=a.test', serial_number: '42', override_field: 'override_unique_subject' } },
})

describe('takenSubject', () => {
  it('recognises the refusal by its status and override field only', () => {
    expect(takenSubject(taken)).toEqual(taken.data.details)
    expect(takenSubject(Object.assign(new Error('x'), { status: 409, data: { details: {} } }))).toBeNull()
    expect(takenSubject(Object.assign(new Error('x'), { status: 400, data: taken.data }))).toBeNull()
  })
})

describe('issueWithSubjectOverride', () => {
  it('asks the operator, naming the subject and the serial, then issues with the override', async () => {
    const issue = vi.fn().mockRejectedValueOnce(taken).mockResolvedValueOnce({ data: { id: 7 } })
    const showConfirm = vi.fn().mockResolvedValue(true)
    expect(await issueWithSubjectOverride(issue, showConfirm, t)).toEqual({ data: { id: 7 } })
    expect(showConfirm.mock.calls[0][0]).toBe('certificates.subjectTakenConfirm:{"subject":"CN=a.test","serial":"42"}')
    expect(issue.mock.calls).toEqual([[{}], [{ override_unique_subject: true }]])
  })

  it('issues nothing when the operator declines', async () => {
    const issue = vi.fn().mockRejectedValueOnce(taken)
    expect(await issueWithSubjectOverride(issue, vi.fn().mockResolvedValue(false), t)).toBeNull()
    expect(issue).toHaveBeenCalledTimes(1)
  })

  it('lets any other error through without asking', async () => {
    const other = Object.assign(new Error('offline'), { status: 400 })
    const showConfirm = vi.fn()
    await expect(issueWithSubjectOverride(vi.fn().mockRejectedValue(other), showConfirm, t)).rejects.toBe(other)
    expect(showConfirm).not.toHaveBeenCalled()
  })
})
