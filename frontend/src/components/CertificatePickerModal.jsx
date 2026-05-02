/**
 * CertificatePickerModal - Modal for selecting a certificate with search + pagination
 * Used in Settings (HTTPS cert) and anywhere a certificate needs to be chosen from a large list.
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  MagnifyingGlass, Certificate, Key, ShieldCheck, CaretLeft, CaretRight, Check
} from '@phosphor-icons/react'
import { Modal, Button, Input, Badge, EmptyState, LoadingSpinner } from '../components'
import { certificatesService } from '../services'
import { formatDate } from '../lib/utils'

export default function CertificatePickerModal({ isOpen, onClose, onSelect, filters = {} }) {
  const { t } = useTranslation()
  const [certificates, setCertificates] = useState([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [selectedId, setSelectedId] = useState(null)
  const perPage = 15

  const loadCertificates = useCallback(async () => {
    setLoading(true)
    try {
      const params = {
        status: filters.status || 'valid',
        page,
        per_page: perPage,
      }
      if (search.trim()) {
        params.search = search.trim()
      }
      const data = await certificatesService.getAll(params)
      const items = data.data || []
      const meta = data.meta || {}

      // Client-side filter for private key + not expired
      const filtered = items.filter(cert => {
        if (filters.has_private_key) {
          return cert.has_private_key && cert.status === 'valid' && new Date(cert.valid_to) > new Date()
        }
        return true
      })

      setCertificates(filtered)
      setTotal(meta.total || filtered.length)
    } catch {
      setCertificates([])
    } finally {
      setLoading(false)
    }
  }, [page, search, filters?.status, filters?.has_private_key])

  useEffect(() => {
    if (isOpen) {
      loadCertificates()
    }
  }, [isOpen, loadCertificates])

  useEffect(() => {
    if (isOpen) {
      setPage(1)
    }
  }, [search, isOpen])

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setSearch('')
      setPage(1)
      setSelectedId(null)
    }
  }, [isOpen])

  const totalPages = Math.max(1, Math.ceil(total / perPage))

  const handleConfirm = () => {
    if (selectedId) {
      const cert = certificates.find(c => c.id === selectedId)
      onSelect(cert)
      onClose()
    }
  }

  return (
    <Modal open={isOpen} onClose={onClose} title={t('settings.selectCertificate')} size="lg">
      <div className="p-4 space-y-4">
        {/* Search */}
        <div className="relative">
          <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('settings.certPickerSearch')}
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-border bg-bg-secondary text-text-primary placeholder:text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent-primary-op30"
          />
        </div>

        {/* Certificate list */}
        <div className="min-h-[320px] max-h-[420px] overflow-y-auto border border-border rounded-lg">
          {loading ? (
            <div className="flex items-center justify-center h-40">
              <LoadingSpinner size="md" />
            </div>
          ) : certificates.length === 0 ? (
            <div className="flex items-center justify-center h-40">
              <EmptyState
                icon={Certificate}
                title={t('settings.noValidCertificates')}
                compact
              />
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-bg-tertiary sticky top-0 z-10">
                <tr className="text-left text-xs text-text-secondary">
                  <th className="px-3 py-2 w-8"></th>
                  <th className="px-3 py-2">{t('common.commonName')}</th>
                  <th className="px-3 py-2 hidden sm:table-cell">{t('common.issuer')}</th>
                  <th className="px-3 py-2">{t('common.validUntil')}</th>
                  <th className="px-3 py-2 hidden sm:table-cell">{t('common.keyType')}</th>
                </tr>
              </thead>
              <tbody>
                {certificates.map(cert => {
                  const isSelected = selectedId === cert.id
                  const daysLeft = Math.ceil((new Date(cert.valid_to) - new Date()) / 86400000)
                  return (
                    <tr
                      key={cert.id}
                      onClick={() => setSelectedId(cert.id)}
                      className={`cursor-pointer border-b border-border transition-colors ${
                        isSelected
                          ? 'bg-accent-primary-op10 border-l-2 border-l-accent-primary'
                          : 'hover:bg-bg-secondary'
                      }`}
                    >
                      <td className="px-3 py-2.5 text-center">
                        {isSelected && <Check size={16} weight="bold" className="text-accent-primary" />}
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="font-medium text-text-primary truncate max-w-[250px]">
                          {cert.common_name || t('common.certificate')}
                        </div>
                        {cert.san_count > 0 && (
                          <div className="text-xs text-text-secondary">
                            +{cert.san_count} SAN{cert.san_count > 1 ? 's' : ''}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2.5 hidden sm:table-cell text-text-secondary truncate max-w-[200px]">
                        {cert.issuer_name || '-'}
                      </td>
                      <td className="px-3 py-2.5">
                        <Badge
                          variant={daysLeft < 30 ? 'warning' : daysLeft < 90 ? 'amber' : 'success'}
                          size="sm"
                        >
                          {formatDate(cert.valid_to)}
                        </Badge>
                      </td>
                      <td className="px-3 py-2.5 hidden sm:table-cell">
                        <span className="text-xs font-mono text-text-secondary">
                          {cert.key_algorithm || '-'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {!loading && total > perPage && (
          <div className="flex items-center justify-between text-xs text-text-secondary">
            <span>{t('common.showingOf', { count: certificates.length, total })}</span>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                size="xs"
                variant="ghost"
                disabled={page <= 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
              >
                <CaretLeft size={14} />
              </Button>
              <span className="px-2">{page} / {totalPages}</span>
              <Button
                type="button"
                size="xs"
                variant="ghost"
                disabled={page >= totalPages}
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              >
                <CaretRight size={14} />
              </Button>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          <Button type="button" variant="secondary" size="sm" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            type="button"
            variant="primary"
            size="sm"
            disabled={!selectedId}
            onClick={handleConfirm}
          >
            <ShieldCheck size={16} />
            {t('settings.applySelectedCertificate')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
