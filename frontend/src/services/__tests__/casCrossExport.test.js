import { describe, it, expect, vi, beforeEach } from 'vitest'

const get = vi.fn().mockResolvedValue({})
vi.mock('../apiClient', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, apiClient: { ...actual.apiClient, get: (...a) => get(...a) } }
})

const { casService } = await import('../cas.service')

beforeEach(() => get.mockClear())

describe('casService.exportCrossCertificate', () => {
  it('sends the requested format', async () => {
    await casService.exportCrossCertificate(1, 2, 'der')
    expect(get.mock.calls[0][0]).toBe('/cas/1/cross-certificates/2/export?format=der')
  })

  it('omits an empty format instead of sending it blank', async () => {
    await casService.exportCrossCertificate(1, 2, '')
    expect(get.mock.calls[0][0]).toBe('/cas/1/cross-certificates/2/export')
  })
})
