import { describe, it, expect, vi } from 'vitest'
import { sharedRequest, dropSharedRequests } from '../sharedRequest'

const later = (value) => new Promise((resolve) => setTimeout(() => resolve(value), 5))

describe('sharedRequest', () => {
  it('runs once for the callers asking while it is in flight', async () => {
    const run = vi.fn(() => later({ data: [1, 2] }))
    const [a, b] = await Promise.all([sharedRequest('k', run), sharedRequest('k', run, { reuseMs: 1000 })])
    expect(run).toHaveBeenCalledTimes(1)
    expect(b).toEqual(a)
  })

  it('gives each caller its own copy, the first one included', async () => {
    const run = () => later({ data: [3, 1, 2] })
    const first = sharedRequest('k', run)
    const second = sharedRequest('k', run, { reuseMs: 1000 })
    const a = await first
    a.data.sort()
    const b = await second
    expect(b.data).toEqual([3, 1, 2])
    const c = await sharedRequest('k', run, { reuseMs: 1000 })
    expect(c.data).toEqual([3, 1, 2])
  })

  it('reads again for a caller that does not opt in, even while a read is in flight', async () => {
    dropSharedRequests()
    const run = vi.fn(() => later({ call: run.mock.calls.length }))
    const poll = sharedRequest('q', run, { reuseMs: 1000 })
    const refresh = await sharedRequest('q', run)
    expect(run).toHaveBeenCalledTimes(2)
    expect(refresh.call).toBe(2)
    expect((await poll).call).toBe(1)
  })

  it('forgets a read still in flight when data changes', async () => {
    dropSharedRequests()
    const run = vi.fn(() => later({ call: run.mock.calls.length }))
    const poll = sharedRequest('q', run, { reuseMs: 1000 })
    window.dispatchEvent(new Event('ucm:data-changed'))
    const opened = await sharedRequest('q', run, { reuseMs: 1000 })
    expect(run).toHaveBeenCalledTimes(2)
    expect(opened.call).toBe(2)
    expect((await poll).call).toBe(1)
  })

  it('asks again once it ended, unless the caller accepts a recent answer', async () => {
    const run = vi.fn(() => later({ n: 1 }))
    await sharedRequest('k', run)
    await sharedRequest('k', run)
    expect(run).toHaveBeenCalledTimes(2)
    await sharedRequest('k', run, { reuseMs: 1000 })
    expect(run).toHaveBeenCalledTimes(2)
  })

  it('does not reuse an answer older than the window, or one a data change outdated', async () => {
    const run = vi.fn(() => later({ n: 1 }))
    await sharedRequest('k', run)
    await new Promise((r) => setTimeout(r, 15))
    await sharedRequest('k', run, { reuseMs: 5 })
    expect(run).toHaveBeenCalledTimes(2)
    window.dispatchEvent(new Event('ucm:data-changed'))
    await sharedRequest('k', run, { reuseMs: 1000 })
    expect(run).toHaveBeenCalledTimes(3)
  })

  it('does not keep a failure', async () => {
    dropSharedRequests()
    const run = vi.fn().mockRejectedValueOnce(new Error('down')).mockResolvedValue({ ok: true })
    await expect(sharedRequest('k', run)).rejects.toThrow('down')
    await expect(sharedRequest('k', run, { reuseMs: 1000 })).resolves.toEqual({ ok: true })
  })
})
