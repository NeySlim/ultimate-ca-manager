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

  afterEach(async () => {
    const { resetLoginRedirect } = await import('../apiClient')
    resetLoginRedirect()
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

  it('keeps the Retry-After of a 429 on the error', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 429,
      headers: new Headers({ 'content-type': 'application/json', 'retry-after': '7' }),
      json: () => Promise.resolve({ error: 'Rate limit exceeded' })
    })
    const { apiClient } = await import('../apiClient')
    await expect(apiClient.get('/acme/client/orders')).rejects.toMatchObject({ status: 429, retryAfter: 7 })
  })

  it('reads Retry-After as seconds or as an HTTP date', async () => {
    const { parseRetryAfter } = await import('../apiClient')
    expect(parseRetryAfter('12')).toBe(12)
    expect(parseRetryAfter(null)).toBeUndefined()
    expect(parseRetryAfter('soon')).toBeUndefined()
    const inFive = new Date(Date.now() + 5000).toUTCString()
    expect(parseRetryAfter(inFive)).toBeGreaterThanOrEqual(4)
    expect(parseRetryAfter(inFive)).toBeLessThanOrEqual(5)
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

    it('carries the page asked for to the login URL', async () => {
      window.location = { pathname: '/certificates', search: '?status=expiring', href: '' }
      global.fetch.mockResolvedValueOnce({
        ok: false, status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ error: 'Unauthorized' })
      })
      const { apiClient } = await import('../apiClient')
      await expect(apiClient.get('/certificates')).rejects.toThrow()
      expect(window.location.href).toBe('/login?next=%2Fcertificates%3Fstatus%3Dexpiring')
    })

    it('redirects once when parallel calls all get 401, and sends no call after', async () => {
      const assigned = []
      window.location = { pathname: '/dashboard', set href(v) { assigned.push(v) }, get href() { return assigned.at(-1) ?? '' } }
      global.fetch.mockResolvedValue({
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ error: 'Unauthorized' })
      })

      const { apiClient } = await import('../apiClient')

      const calls = ['/certificates', '/cas', '/dashboard/stats'].map(e => apiClient.get(e))
      await Promise.allSettled(calls)
      expect(assigned).toEqual(['/login'])
      const sent = global.fetch.mock.calls.length

      await expect(apiClient.get('/certificates')).rejects.toMatchObject({ status: 401 })
      expect(global.fetch.mock.calls.length).toBe(sent)
      expect(assigned).toEqual(['/login'])
    })

    it('a page restored from the back-forward cache sends its calls again', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ error: 'Unauthorized' })
      })
      const { apiClient } = await import('../apiClient')
      await expect(apiClient.get('/certificates')).rejects.toThrow()
      expect(window.location.href).toBe('/login')

      window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: false }))
      await expect(apiClient.get('/certificates')).rejects.toMatchObject({ status: 401 })
      // The refused call and the session check that found no session
      expect(global.fetch).toHaveBeenCalledTimes(2)

      window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }))
      global.fetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ data: [] })
      })
      await expect(apiClient.get('/certificates')).resolves.toEqual({ data: [] })
      expect(global.fetch).toHaveBeenCalledTimes(3)
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

  describe('401 after the session identifier was renewed', () => {
    const GATE = 'urn:ucm:problem:authentication-required'
    const json = (status, body) => ({
      ok: status >= 200 && status < 300,
      status,
      headers: new Headers({ 'content-type': status < 300 ? 'application/json' : 'application/problem+json' }),
      json: () => Promise.resolve(body),
    })
    const refused = (type = GATE) => json(401, { type, status: 401, message: 'Authentication required' })
    const session = authenticated => json(200, { data: authenticated
      ? { authenticated: true, csrf_token: 'fresh-token' } : { authenticated: false } })
    const urls = () => global.fetch.mock.calls.map(([url]) => url)
    let assigned
    beforeEach(() => {
      assigned = []
      window.location = { pathname: '/account', search: '', set href(v) { assigned.push(v) }, get href() { return assigned.at(-1) ?? '' } }
    })

    it('sends the refused call again once when the current session is open', async () => {
      global.fetch
        .mockResolvedValueOnce(refused())
        .mockResolvedValueOnce(session(true))
        .mockResolvedValueOnce(json(200, { data: { username: 'u' } }))
      const { apiClient } = await import('../apiClient')
      await expect(apiClient.get('/account/profile')).resolves.toEqual({ data: { username: 'u' } })
      expect(urls()).toEqual(['/api/v2/account/profile', '/api/v2/auth/verify', '/api/v2/account/profile'])
      expect(assigned).toEqual([])
    })

    it('signs out when the current session is gone, and sends nothing again', async () => {
      global.fetch.mockResolvedValueOnce(refused()).mockResolvedValueOnce(session(false))
      const { apiClient } = await import('../apiClient')
      await expect(apiClient.get('/account/profile')).rejects.toMatchObject({ status: 401 })
      expect(urls()).toEqual(['/api/v2/account/profile', '/api/v2/auth/verify'])
      expect(assigned).toEqual(['/login?next=%2Faccount'])
    })

    it('signs out when the session check cannot answer', async () => {
      global.fetch.mockResolvedValueOnce(refused()).mockRejectedValueOnce(new TypeError('offline'))
      const { apiClient } = await import('../apiClient')
      await expect(apiClient.get('/account/profile')).rejects.toMatchObject({ status: 401 })
      expect(assigned).toEqual(['/login?next=%2Faccount'])
    })

    it('checks the session once for a burst of 401s, and sends each call again once', async () => {
      let answer
      const check = new Promise(resolve => { answer = resolve })
      global.fetch.mockImplementation(async (url) => {
        if (url === '/api/v2/auth/verify') return check
        return global.fetch.mock.calls.filter(([u]) => u === url).length === 1 ? refused() : json(200, { data: url })
      })
      const { apiClient } = await import('../apiClient')
      const calls = ['/certificates', '/cas', '/dashboard/stats'].map(e => apiClient.get(e))
      await vi.waitFor(() => expect(urls().filter(u => u !== '/api/v2/auth/verify')).toHaveLength(3))
      await new Promise(resolve => setTimeout(resolve, 0))
      answer(session(true))
      await expect(Promise.all(calls)).resolves.toEqual([
        { data: '/api/v2/certificates' }, { data: '/api/v2/cas' }, { data: '/api/v2/dashboard/stats' }])
      expect(urls().filter(u => u === '/api/v2/auth/verify')).toHaveLength(1)
      expect(urls()).toHaveLength(7)
      expect(assigned).toEqual([])
    })

    it('signs out when the call sent again gets 401, without checking again', async () => {
      global.fetch
        .mockResolvedValueOnce(refused())
        .mockResolvedValueOnce(session(true))
        .mockResolvedValueOnce(refused())
        .mockResolvedValue(session(true))
      const { apiClient } = await import('../apiClient')
      await expect(apiClient.get('/account/profile')).rejects.toMatchObject({ status: 401 })
      expect(urls()).toEqual(['/api/v2/account/profile', '/api/v2/auth/verify', '/api/v2/account/profile'])
      expect(assigned).toEqual(['/login?next=%2Faccount'])
    })

    it("keeps the page and sends nothing again when the 401 is the route's own answer", async () => {
      global.fetch
        .mockResolvedValueOnce(refused('about:blank'))
        .mockResolvedValue(session(true))
      const { apiClient } = await import('../apiClient')
      await expect(apiClient.post('/cas/1/restore', { password: 'wrong' })).rejects.toMatchObject({ status: 401 })
      expect(urls()).toEqual(['/api/v2/cas/1/restore', '/api/v2/auth/verify'])
      expect(assigned).toEqual([])
    })

    it('sends a refused change again with the CSRF token of the session check', async () => {
      let stored = 'old-token'
      Storage.prototype.getItem.mockImplementation(() => stored)
      Storage.prototype.setItem.mockImplementation((_key, value) => { stored = value })
      global.fetch
        .mockResolvedValueOnce(refused())
        .mockResolvedValueOnce(session(true))
        .mockResolvedValueOnce(json(200, { data: { saved: true } }))
      const { apiClient } = await import('../apiClient')
      await expect(apiClient.patch('/account/profile', { full_name: 'N' })).resolves.toEqual({ data: { saved: true } })
      const [, first] = global.fetch.mock.calls[0]
      const [, again] = global.fetch.mock.calls[2]
      expect(first.headers['X-CSRF-Token']).toBe('old-token')
      expect(again).toMatchObject({ method: 'PATCH', body: JSON.stringify({ full_name: 'N' }) })
      expect(again.headers['X-CSRF-Token']).toBe('fresh-token')
    })

    it('while a restore holds the sign-out, a 401 neither checks the session nor signs out', async () => {
      global.fetch.mockResolvedValue(refused())
      const { apiClient, holdSignOut } = await import('../apiClient')
      holdSignOut()
      await expect(apiClient.get('/certificates/stats')).rejects.toMatchObject({ status: 401 })
      expect(urls()).toEqual(['/api/v2/certificates/stats'])
      expect(assigned).toEqual([])

      holdSignOut(false)
      global.fetch.mockResolvedValueOnce(refused()).mockResolvedValueOnce(session(false))
      await expect(apiClient.get('/certificates/stats')).rejects.toMatchObject({ status: 401 })
      expect(assigned).toEqual(['/login?next=%2Faccount'])
    })
  })
})
