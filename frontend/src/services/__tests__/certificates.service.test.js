/**
 * Certificates Service Tests
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { certificatesService } from '../certificates.service'
import { apiClient } from '../apiClient'

vi.mock('../apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn()
  }
}))

describe('Certificates Service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getAll', () => {
    it('calls GET /certificates without filters', async () => {
      apiClient.get.mockResolvedValue({ data: [] })
      
      await certificatesService.getAll()
      
      expect(apiClient.get).toHaveBeenCalledWith('/certificates')
    })

    it('calls GET /certificates with all filters', async () => {
      apiClient.get.mockResolvedValue({ data: [] })
      
      await certificatesService.getAll({
        status: 'valid',
        issuer: 'Root CA',
        search: 'test',
        page: 2,
        per_page: 50
      })
      
      expect(apiClient.get).toHaveBeenCalledWith(
        '/certificates?status=valid&issuer=Root+CA&search=test&page=2&per_page=50'
      )
    })

    it('calls GET /certificates with partial filters', async () => {
      apiClient.get.mockResolvedValue({ data: [] })
      
      await certificatesService.getAll({ status: 'expired' })
      
      expect(apiClient.get).toHaveBeenCalledWith('/certificates?status=expired')
    })
  })

  describe('getById', () => {
    it('calls GET /certificates/:id', async () => {
      apiClient.get.mockResolvedValue({ data: { id: 1 } })
      
      await certificatesService.getById(1)
      
      expect(apiClient.get).toHaveBeenCalledWith('/certificates/1')
    })
  })

  describe('revoke', () => {
    it('calls POST /certificates/:id/revoke with reason', async () => {
      apiClient.post.mockResolvedValue({ message: 'Revoked' })
      
      await certificatesService.revoke(1, 'key_compromise')
      
      expect(apiClient.post).toHaveBeenCalledWith('/certificates/1/revoke', {
        reason: 'key_compromise'
      })
    })

    it('uses undefined reason if not provided', async () => {
      apiClient.post.mockResolvedValue({ message: 'Revoked' })
      
      await certificatesService.revoke(5)
      
      expect(apiClient.post).toHaveBeenCalledWith('/certificates/5/revoke', {
        reason: undefined
      })
    })
  })

  describe('renew', () => {
    it('calls POST /certificates/:id/renew', async () => {
      apiClient.post.mockResolvedValue({ data: { id: 2 } })
      
      await certificatesService.renew(1)
      
      expect(apiClient.post).toHaveBeenCalledWith('/certificates/1/renew')
    })
  })

  describe('export', () => {
    it('calls GET /certificates/:id/export with format', async () => {
      apiClient.get.mockResolvedValue({ data: 'PEM data' })
      
      await certificatesService.export(1, 'pem')
      
      expect(apiClient.get).toHaveBeenCalledWith('/certificates/1/export?format=pem', {
        responseType: 'blob'
      })
    })

    it('uses default format if not provided', async () => {
      apiClient.get.mockResolvedValue({ data: 'PEM data' })
      
      await certificatesService.export(1)
      
      expect(apiClient.get).toHaveBeenCalledWith('/certificates/1/export?format=pem', {
        responseType: 'blob'
      })
    })

    it('includes options in query string', async () => {
      apiClient.get.mockResolvedValue({ data: 'PEM data' })
      
      await certificatesService.export(1, 'pkcs12', { includeKey: true, includeChain: true })
      
      expect(apiClient.get).toHaveBeenCalledWith(
        '/certificates/1/export?format=pkcs12&include_key=true&include_chain=true',
        { responseType: 'blob' }
      )
    })

    it('includes password option', async () => {
      apiClient.get.mockResolvedValue({ data: 'PKCS12 data' })
      
      await certificatesService.export(1, 'pkcs12', { password: 'secret123' })
      
      expect(apiClient.get).toHaveBeenCalledWith(
        '/certificates/1/export?format=pkcs12&password=secret123',
        { responseType: 'blob' }
      )
    })
  })

  describe('create', () => {
    it('calls POST /certificates with data', async () => {
      apiClient.post.mockResolvedValue({ data: { id: 1 } })
      
      await certificatesService.create({ common_name: 'test.com', ca_id: 1 })
      
      expect(apiClient.post).toHaveBeenCalledWith('/certificates', {
        common_name: 'test.com',
        ca_id: 1
      })
    })
  })

  describe('delete', () => {
    it('calls DELETE /certificates/:id', async () => {
      apiClient.delete.mockResolvedValue({ message: 'Deleted' })
      
      await certificatesService.delete(1)
      
      expect(apiClient.delete).toHaveBeenCalledWith('/certificates/1')
    })
  })
})
