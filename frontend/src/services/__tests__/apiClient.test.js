import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock the apiClient module directly since it's a singleton
describe('API Client', () => {
  const originalFetch = global.fetch

  beforeEach(() => {
    global.fetch = vi.fn()
  })

  afterEach(() => {
    global.fetch = originalFetch
    vi.clearAllMocks()
  })

  it('makes GET request with correct URL', async () => {
    const mockResponse = {
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ data: [] })
    }
    global.fetch.mockResolvedValueOnce(mockResponse)

    // Import after mock setup
    const { apiClient } = await import('../apiClient')
    await apiClient.get('/certificates')

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/v2/certificates',
      expect.objectContaining({
        method: 'GET',
        credentials: 'include'
      })
    )
  })

  it('makes POST request with body', async () => {
    const mockResponse = {
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ data: { id: 1 } })
    }
    global.fetch.mockResolvedValueOnce(mockResponse)

    const { apiClient } = await import('../apiClient')
    await apiClient.post('/certificates', { name: 'Test' })

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/v2/certificates',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'Test' }),
        headers: expect.objectContaining({
          'Content-Type': 'application/json'
        })
      })
    )
  })

  it('handles error responses', async () => {
    const mockResponse = {
      ok: false,
      status: 404,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ error: true, message: 'Not found' })
    }
    global.fetch.mockResolvedValueOnce(mockResponse)

    const { apiClient } = await import('../apiClient')
    await expect(apiClient.get('/invalid')).rejects.toThrow()
  })

  it('handles network errors', async () => {
    global.fetch.mockRejectedValueOnce(new Error('Network error'))

    const { apiClient } = await import('../apiClient')
    await expect(apiClient.get('/test')).rejects.toThrow('Network error')
  })

  it('makes PATCH request correctly', async () => {
    const mockResponse = {
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ data: { updated: true } })
    }
    global.fetch.mockResolvedValueOnce(mockResponse)

    const { apiClient } = await import('../apiClient')
    await apiClient.patch('/certificates/1', { name: 'Updated' })

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/v2/certificates/1',
      expect.objectContaining({
        method: 'PATCH'
      })
    )
  })

  it('makes DELETE request correctly', async () => {
    const mockResponse = {
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ message: 'Deleted' })
    }
    global.fetch.mockResolvedValueOnce(mockResponse)

    const { apiClient } = await import('../apiClient')
    await apiClient.delete('/certificates/1')

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/v2/certificates/1',
      expect.objectContaining({
        method: 'DELETE'
      })
    )
  })
})
