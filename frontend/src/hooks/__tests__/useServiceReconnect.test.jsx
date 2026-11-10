/**
 * started_at is compared per node_id: a different node answering behind a
 * balancer is not a restart of the node the page was talking to.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useServiceReconnect } from '../useServiceReconnect'

const tick = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })
const MINUTE = 60 * 1000
const answer = { body: {} }

describe('useServiceReconnect node_id handling', () => {
  const realFetch = globalThis.fetch
  beforeEach(() => {
    vi.useFakeTimers()
    answer.body = { started_at: 100, node_id: 'a', websocket: true }
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => answer.body }))
  })
  afterEach(() => {
    vi.useRealTimers()
    globalThis.fetch = realFetch
  })

  async function startAndCountdown() {
    const hook = renderHook(() => useServiceReconnect())
    act(() => { hook.result.current.waitForRestart() })
    await tick(0)
    await tick(MINUTE)
    return hook
  }

  it('keeps waiting when another node answers with a newer started_at', async () => {
    const { result } = await startAndCountdown()
    answer.body = { started_at: 500, node_id: 'b', websocket: true }
    await tick(6000)
    expect(result.current.status).toBe('connecting')
  })

  it('reconnects when the same node reports a newer started_at', async () => {
    const { result } = await startAndCountdown()
    answer.body = { started_at: 500, node_id: 'a', websocket: true }
    await tick(3000)
    expect(result.current.status).toBe('redirecting')
  })
})
