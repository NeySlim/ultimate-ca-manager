/**
 * The Chaîne panel: the mockup's chainDetail(), one box per CA from the anchor down (its role and
 * key, Inspecter l'autorité), then the certificate; then the product's chain state, the offer to
 * trust the issuer of an incomplete chain and the variants a cross-certificate serves.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../../components/atelier'
import { chainNodes, certificateKeyLabel } from '../../../lib/certificateDetail'
import { extractCN } from '../../../lib/utils'
import { usePermission } from '../../../hooks'
import { casService } from '../../../services'
import { useAddIssuerToTrustStore } from './useAddIssuerToTrustStore'
import { CertBadge } from '../CertBadge'

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

const STATUS_KEY = { complete: 'details.chainComplete', incomplete: 'details.chainIncomplete', partial: 'details.chainPartial' }

export function ChainPanel({ cert, title, openCa, onChanged }) {
  const { t } = useTranslation()
  const trust = useAddIssuerToTrustStore(cert, onChanged)
  const nodes = chainNodes(cert)
  const issuer = cert.issuer_name || extractCN(cert.issuer)
  const shown = nodes.length ? nodes : (issuer ? [{ name: issuer, role: 'intermediate', level: 1, issuing: true }] : [])
  const status = cert.chain_status?.status
  const variants = cert.chain_status?.variants?.length || 0
  const cols = Array(shown.length + 1).fill('minmax(0,1fr)').join(' 40px ')
  const caKeys = useCaKeys(shown.map((n) => n.name).filter(Boolean), t)
  const role = (n) => (n.role === 'root' ? t('inspector.cert.rootCa') : n.role === 'anchor' ? t('inspector.cert.trustStoreAnchor') : t('inspector.cert.intermediateCa', { level: n.level }))

  return (
    <>
      <div className="chain-canvas" style={{ '--chain-cols': cols }} data-testid="certificate-chain">
        {shown.map((n, i) => [
          <section key={`box-${i}`} className="chain-box">
            <header><Icon name={n.role === 'intermediate' ? 'branch' : 'shield'} />{n.name}</header>
            <p>{[role(n), caKeys[n.name]].filter(Boolean).join(' · ')}</p>
            {openCa && n.type !== 'trust_store' && (
              <button type="button" className="text-link" data-ca-go={n.name} onClick={() => openCa(n.name, { issuing: n.issuing })}>{t('inspector.cert.inspectCa')}</button>
            )}
            {n.cross && <> <span className="chip cross"><Icon name="link" />{t('inspector.cert.crossSigned')}</span></>}
          </section>,
          <div key={`link-${i}`} className="connector" aria-hidden="true" />,
        ])}
        <section className="chain-box selected">
          <header><Icon name="cert" /><span>{title}</span></header>
          <p>{[cert.template_name, certificateKeyLabel(cert, t)].filter(Boolean).join(' · ') || '—'}</p>
          <CertBadge cert={cert} t={t} />
        </section>
      </div>
      {status && STATUS_KEY[status] && (
        <p className={status === 'incomplete' ? 'chain-cross warn' : 'chain-cross'}>
          <Icon name={status === 'complete' ? 'check' : 'warning'} />
          <span>
            {t(STATUS_KEY[status])}
            {cert.chain_status.trust_anchor && <> · {t('inspector.cert.trustAnchorLine', { name: cert.chain_status.trust_anchor })}</>}
            {status === 'incomplete' && <> {t('details.chainIncompleteHint')}</>}
          </span>
        </p>
      )}
      {status === 'incomplete' && trust.offered && (
        <p className="chain-cross">
          <button type="button" className="btn" onClick={trust.add} disabled={trust.adding} data-write="">
            <Icon name="shield" />{t('details.addIssuerToTrustStore')}
          </button>
        </p>
      )}
      {variants > 1 && <p className="chain-cross"><Icon name="layers" /><span>{t('inspector.cert.variants', { count: variants })}</span></p>}
    </>
  )
}
