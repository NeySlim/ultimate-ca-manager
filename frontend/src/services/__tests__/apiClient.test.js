import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock the apiClient module directly since it's a singleton
describe('API Client', () => {
  const originalFetch = global.fetch
  const originalLocation = window.location

  beforeEach(() => {
    global.fetch = vi.fn()
    // Mock sessionStorage
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {})
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {})
    // Mock window.location
    delete window.location
    window.location = { pathname: '/dashboard', href: '' }
  })

  afterEach(() => {
    global.fetch = originalFetch
    window.location = originalLocation
    vi.clearAllMocks()
    vi.restoreAllMocks()
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

  it('makes PUT request correctly', async () => {
    const mockResponse = {
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ data: { updated: true } })
    }
    global.fetch.mockResolvedValueOnce(mockResponse)

    const { apiClient } = await import('../apiClient')
    await apiClient.put('/certificates/1', { name: 'Updated' })

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/v2/certificates/1',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ name: 'Updated' })
      })
    )
  })

  describe('CSRF Token', () => {
    it('stores CSRF token', async () => {
      const { apiClient } = await import('../apiClient')
      apiClient.setCsrfToken('test-token')
      expect(Storage.prototype.setItem).toHaveBeenCalledWith('ucm_csrf_token', 'test-token')
    })

    it('clears CSRF token', async () => {
      const { apiClient } = await import('../apiClient')
      apiClient.clearCsrfToken()
      expect(Storage.prototype.removeItem).toHaveBeenCalledWith('ucm_csrf_token')
    })

    it('includes CSRF token in POST requests', async () => {
      vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('csrf-token-123')
      
      const mockResponse = {
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true })
      }
      global.fetch.mockResolvedValueOnce(mockResponse)

      const { apiClient } = await import('../apiClient')
      await apiClient.post('/test', { data: 'test' })

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v2/test',
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-CSRF-Token': 'csrf-token-123'
          })
        })
      )
    })
  })

  describe('Upload', () => {
    it('uploads FormData correctly', async () => {
      const mockResponse = {
        ok: true,
        json: () => Promise.resolve({ success: true, file: 'test.pem' })
      }
      global.fetch.mockResolvedValueOnce(mockResponse)

      const { apiClient } = await import('../apiClient')
      const formData = new FormData()
      formData.append('file', new Blob(['test']), 'test.pem')
      
      const result = await apiClient.upload('/import', formData)

      expect(result).toEqual({ success: true, file: 'test.pem' })
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v2/import',
        expect.objectContaining({
          method: 'POST',
          body: formData,
          credentials: 'include'
        })
      )
    })

    it('handles upload errors', async () => {
      const mockResponse = {
        ok: false,
        status: 400,
        json: () => Promise.resolve({ error: 'Invalid file' })
      }
      global.fetch.mockResolvedValueOnce(mockResponse)

      const { apiClient } = await import('../apiClient')
      const formData = new FormData()
      
      await expect(apiClient.upload('/import', formData)).rejects.toThrow()
    })

    it('handles upload network errors', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Network failure'))

      const { apiClient } = await import('../apiClient')
      const formData = new FormData()
      
      await expect(apiClient.upload('/import', formData)).rejects.toThrow('Network error')
    })
  })

  describe('Download', () => {
    it('downloads file as blob', async () => {
      const mockBlob = new Blob(['certificate content'], { type: 'application/x-pem-file' })
      const mockResponse = {
        ok: true,
        blob: () => Promise.resolve(mockBlob)
      }
      global.fetch.mockResolvedValueOnce(mockResponse)

      const { apiClient } = await import('../apiClient')
      const result = await apiClient.download('/certificates/1/download')

      expect(result).toEqual(mockBlob)
    })

    it('handles download errors', async () => {
      const mockResponse = {
        ok: false,
        status: 404
      }
      global.fetch.mockResolvedValueOnce(mockResponse)

      const { apiClient } = await import('../apiClient')
      
      await expect(apiClient.download('/certificates/999/download')).rejects.toThrow('The requested resource was not found.')
    })
  })

  describe('Response handling', () => {
    it('handles text responses', async () => {
      const mockResponse = {
        ok: true,
        headers: new Headers({ 'content-type': 'text/plain' }),
        text: () => Promise.resolve('Plain text response')
      }
      global.fetch.mockResolvedValueOnce(mockResponse)

      const { apiClient } = await import('../apiClient')
      const result = await apiClient.get('/text-endpoint')

      expect(result).toBe('Plain text response')
    })

    it('handles blob response type', async () => {
      const mockBlob = new Blob(['binary data'])
      const mockResponse = {
        ok: true,
        headers: new Headers({ 'content-type': 'application/octet-stream' }),
        blob: () => Promise.resolve(mockBlob)
      }
      global.fetch.mockResolvedValueOnce(mockResponse)

      const { apiClient } = await import('../apiClient')
      const result = await apiClient.get('/binary', { responseType: 'blob' })

      expect(result).toEqual(mockBlob)
    })
  })

  describe('401 Handling', () => {
    it('redirects to login on 401 for non-auth endpoints', async () => {
      window.location = { pathname: '/dashboard', href: '' }
      
      const mockResponse = {
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ error: 'Unauthorized' })
      }
      global.fetch.mockResolvedValueOnce(mockResponse)

      const { apiClient } = await import('../apiClient')
      
      await expect(apiClient.get('/certificates')).rejects.toThrow()
      expect(window.location.href).toBe('/login')
    })

    it('does not redirect on 401 when already on login page', async () => {
      window.location = { pathname: '/login', href: '' }
      
      const mockResponse = {
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ error: 'Unauthorized' })
      }
      global.fetch.mockResolvedValueOnce(mockResponse)

      const { apiClient } = await import('../apiClient')
      
      await expect(apiClient.get('/test')).rejects.toThrow()
      expect(window.location.href).toBe('')
    })

    it('does not redirect on 401 for auth endpoints', async () => {
      window.location = { pathname: '/dashboard', href: '' }
      
      const mockResponse = {
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ error: 'Invalid credentials' })
      }
      global.fetch.mockResolvedValueOnce(mockResponse)

      const { apiClient } = await import('../apiClient')
      
      await expect(apiClient.post('/auth/login', { username: 'test' })).rejects.toThrow()
      expect(window.location.href).toBe('')
    })
  })
})
