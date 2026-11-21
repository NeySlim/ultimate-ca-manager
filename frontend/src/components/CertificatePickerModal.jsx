/**
 * A certificate picked from the server's list, in the mockup's dialog: the command palette's
 * search and results (`.command-search`, `.command-result`), a click picks, then the table
 * footer pages the list the server holds. Used by Settings (the HTTPS certificate).
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from './atelier/AtelierDialog'
import { Icon } from './atelier/Icon'
import { TableFooter } from './atelier/TableFooter'
import { certificatesService } from '../services'
import { daysRemaining, formatDate, certificateNames } from '../lib/utils'

const PER_PAGE = 15

export default function CertificatePickerModal({ isOpen, ...props }) {
  return isOpen ? <Picker {...props} /> : null
}

function Picker({ onClose, onSelect, filters = {} }) {
  const { t } = useTranslation()
  const [certificates, setCertificates] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  // A string key keeps the callback stable when the caller passes a fresh array
  const statusKey = [].concat(filters.status || 'valid').join(',')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = { status: statusKey.split(','), page, per_page: PER_PAGE }
      if (search.trim()) params.search = search.trim()
      if (filters.has_private_key) params.has_private_key = true
      const data = await certificatesService.getAll(params)
      const items = data.data || []
      setCertificates(items)
      setTotal(data.meta?.total ?? items.length)
    } catch {
      setCertificates([])
    } finally {
      setLoading(false)
    }
  }, [page, search, statusKey, filters?.has_private_key])

  useEffect(() => { load() }, [load])

  const pages = Math.max(1, Math.ceil(total / PER_PAGE))
  const pick = (cert) => {
    onSelect(cert)
    onClose()
  }

  return (
    <AtelierDialog title={t('settings.selectCertificate')} onClose={onClose} testId="certificate-picker">
      <div className="command-search">
        <Icon name="search" />
        <input type="search" data-autofocus aria-label={t('settings.certPickerSearch')} placeholder={t('settings.certPickerSearch')}
          value={search} autoComplete="off" spellCheck={false} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
      </div>
      {loading ? (
        <p className="small muted" role="status">{t('common.loading')}</p>
      ) : certificates.length === 0 ? (
        <p className="event-detail">{t('settings.noValidCertificates')}</p>
      ) : (
        <div className="command-results">
          {certificates.map((cert) => {
            const { name, subtitle } = certificateNames(cert)
            const left = daysRemaining(cert.valid_to)
            const facts = [
              cert.san_count > 1 && `${cert.san_count} ${t('details.sans')}`,
              cert.issuer_name,
              `${t('common.validUntil')} ${formatDate(cert.valid_to)}`,
            ].filter(Boolean).join(' · ')
            return (
              <button key={cert.id} type="button" className="command-result" onClick={() => pick(cert)}>
                <Icon name="cert" />
                <span className="name">
                  <span>
                    <strong>{name || t('common.certificate')}</strong>
                    {subtitle && <span className="muted" title={subtitle}> · {subtitle}</span>}
                  </span>
                  <small className={left < 30 ? 'warn' : 'muted'} style={{ display: 'block' }}>{facts}</small>
                </span>
                {cert.key_algorithm && <span className="hint mono">{cert.key_algorithm}</span>}
              </button>
            )
          })}
        </div>
      )}
      {!loading && total > PER_PAGE && (
        <TableFooter range={t('common.showingOf', { count: certificates.length, total })} pagination={{ page, pages, onPage: setPage }} />
      )}
    </AtelierDialog>
  )
}
