/**
 * Chain of a certificate: one box per CA from the anchor down, each with its role
 * and key, then the certificate itself (template and key); side by side under the
 * list, stacked in a narrow dock. The state of the chain, its served variants and,
 * for an incomplete chain, the offer to trust the issuing CA follow the boxes.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldCheck, TreeStructure, Certificate, Warning, LinkSimple, CheckCircle, Stack } from '@phosphor-icons/react'
import { chainNodes, certificateKeyLabel } from '../../../lib/certificateDetail'
import { extractCN } from '../../../lib/utils'
import { StatusPill } from '../../list'
import { certificateState } from '../../../pages/certificates/useCertificateColumns'
import { usePermission } from '../../../hooks'
import { useNotification } from '../../../contexts'
import { certificatesService, truststoreService, casService } from '../../../services'

/** Adds the issuing CA of an incomplete chain to the trust store; the chain is read again after. */
export function useAddIssuerToTrustStore(cert, onChanged) {
  const { t } = useTranslation()
  const { canWrite } = usePermission()
  const { showSuccess, showError } = useNotification()
  const [adding, setAdding] = useState(false)
  const offered = cert?.chain_status?.status === 'incomplete' && !!cert?.caref && canWrite('truststore')
  const add = async () => {
    setAdding(true)
    try {
      await truststoreService.addFromCA(cert.caref)
      showSuccess(t('details.addedToTrustStore'))
      const res = await certificatesService.getById(cert.id)
      if (res?.data) onChanged?.({ ...cert, ...res.data })
    } catch (err) {
      showError(err?.message || t('details.addToTrustStoreFailed'))
    } finally {
      setAdding(false)
    }
  }
  return { offered, adding, add }
}

// The chain links carry names only: the key of each CA comes from the CA list, when it may be read
function useCaKeys(names, t) {
  const { hasPermission } = usePermission()
  const [keys, setKeys] = useState({})
  const wanted = names.length > 0 && hasPermission('read:cas')
  const key = names.join('|')
  useEffect(() => {
    if (!wanted) return undefined
    let cancelled = false
    casService.getAll()
      .then((res) => {
        if (cancelled) return
        const out = {}
        for (const ca of res?.data || []) {
          const label = certificateKeyLabel(ca, t)
          if (label) for (const n of [ca.common_name, ca.descr, ca.name]) if (n && !(n in out)) out[n] = label
        }
        setKeys(out)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [wanted, key]) // eslint-disable-line react-hooks/exhaustive-deps
  return keys
}

const STATUS_TONE = { complete: 'good', incomplete: 'warn', partial: '' }
const STATUS_KEY = { complete: 'details.chainComplete', incomplete: 'details.chainIncomplete', partial: 'details.chainPartial' }

export function CertificateChain({ cert, title, columns, openCa, onChanged }) {
  const { t } = useTranslation()
  const trust = useAddIssuerToTrustStore(cert, onChanged)
  const nodes = chainNodes(cert)
  const issuer = cert.issuer_name || extractCN(cert.issuer)
  const shown = nodes.length ? nodes : (issuer ? [{ name: issuer, role: 'intermediate', level: 1, issuing: true }] : [])
  const status = cert.chain_status?.status
  const variants = cert.chain_status?.variants?.length || 0
  const cols = Array(shown.length + 1).fill('minmax(0, 1fr)').join(' 40px ')
  const caKeys = useCaKeys(shown.map((n) => n.name).filter(Boolean), t)
  const leafLine = [cert.template_name, certificateKeyLabel(cert, t)].filter(Boolean).join(' · ') || '—'

  const role = (n) => {
    if (n.role === 'root') return t('inspector.cert.rootCa')
    if (n.role === 'anchor') return t('inspector.cert.trustStoreAnchor')
    return t('inspector.cert.intermediateCa', { level: n.level })
  }

  return (
    <div data-testid="certificate-chain">
      <div className="ins-chain" data-columns={columns} style={{ '--chain-cols': cols }}>
        {shown.map((n, i) => [
          <section key={`box-${i}`} className="ins-chain-box">
            <header>
              {n.role === 'intermediate' ? <TreeStructure size={15} aria-hidden="true" /> : <ShieldCheck size={15} aria-hidden="true" />}
              <span>{n.name}</span>
            </header>
            <p>{[role(n), caKeys[n.name]].filter(Boolean).join(' · ')}</p>
            {openCa && n.type !== 'trust_store' && (
              <button type="button" className="ins-link" onClick={() => openCa(n.name, { issuing: n.issuing })}>
                {t('inspector.cert.inspectCa')}
              </button>
            )}
            {n.cross && <span className="ins-chip"><LinkSimple size={12} aria-hidden="true" />{t('inspector.cert.crossSigned')}</span>}
          </section>,
          <div key={`link-${i}`} className="ins-connector" aria-hidden="true" />,
        ])}
        <section className="ins-chain-box is-selected">
          <header><Certificate size={15} aria-hidden="true" /><span>{title}</span></header>
          <p>{leafLine}</p>
          <StatusPill {...certificateState(cert, t)} />
        </section>
      </div>
      {status && STATUS_KEY[status] && (
        <p className="ins-chain-status">
          <span className={`ins-chip${STATUS_TONE[status] ? ` is-${STATUS_TONE[status]}` : ''}`}>
            {status === 'complete' ? <CheckCircle size={12} aria-hidden="true" /> : <Warning size={12} aria-hidden="true" />}
            {t(STATUS_KEY[status])}
          </span>
          {cert.chain_status.trust_anchor && (
            <span className="ins-muted">{t('inspector.cert.trustAnchorLine', { name: cert.chain_status.trust_anchor })}</span>
          )}
        </p>
      )}
      {status === 'incomplete' && (
        <div className="ins-note is-warn">
          <Warning size={13} aria-hidden="true" />
          <div>
            <p className="m-0">{t('details.chainIncompleteHint')}</p>
            {trust.offered && (
              <button type="button" className="lv-btn" style={{ marginTop: 8 }} onClick={trust.add} disabled={trust.adding}>
                <ShieldCheck size={14} aria-hidden="true" />{t('details.addIssuerToTrustStore')}
              </button>
            )}
          </div>
        </div>
      )}
      {variants > 1 && (
        <p className="ins-note"><Stack size={13} aria-hidden="true" />{t('inspector.cert.variants', { count: variants })}</p>
      )}
    </div>
  )
}
