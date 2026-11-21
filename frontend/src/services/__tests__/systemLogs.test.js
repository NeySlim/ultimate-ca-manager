import { describe, it, expect, vi, beforeEach } from 'vitest'

const get = vi.fn().mockResolvedValue({})
vi.mock('../apiClient', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, apiClient: { ...actual.apiClient, get: (...a) => get(...a) } }
})

const { systemService } = await import('../system.service')

beforeEach(() => get.mockClear())

describe('systemService.getLogs', () => {
  it('sends the count under the name the route reads (lines)', async () => {
    await systemService.getLogs(250)
    expect(get.mock.calls[0][0]).toBe('/system/logs?lines=250')
  })
})
