/**
 * Chain of a certificate: one box per authority, root first, the certificate last, then
 * what the server says of the chain and the issuer the certificate names.
 */
import { useTranslation } from 'react-i18next'
import { Certificate, ShieldCheck, TreeStructure, Warning, CheckCircle, LinkSimple, Vault } from '@phosphor-icons/react'
import { cn, extractCN } from '../../../lib/utils'
import { keyAlgorithmLabel } from '../../../lib/keyAlgorithms'
import { certificateState } from '../../../lib/certificateState'
import { StatusPill } from '../../list/StatusPill'
import { chainPath, chainSentence } from './chainPath'

export function CertificateChain({ certificate, onOpenIssuer, onAddToTrustStore }) {
  const { t } = useTranslation()
  const cert = certificate
  const chain = chainPath(cert)
  const sentence = chainSentence(chain, t)
  const name = cert.cn || cert.common_name || extractCN(cert.subject) || ''
  const keyName = keyAlgorithmLabel(cert.key_algorithm || cert.key_type, t, cert.security_level)
  const cols = Array(chain.path.length + 1).fill('minmax(0,1fr)').join(' 40px ')
  const role = (node) => {
    if (node.kind === 'store') return t('inspector.cert.storeAnchor')
    if (node.kind === 'unknown') return t('inspector.cert.issuerNotHeld')
    if (node.root) return t('inspector.cert.rootAuthority')
    return node.level ? t('inspector.cert.intermediateLevel', { level: node.level }) : t('inspector.cert.intermediate')
  }

  return (
    <>
      <div className="insp-chain" style={{ '--insp-chain-cols': cols }} data-testid="chain-canvas">
        {chain.path.map((node, i) => [
          <section key={`box-${i}`} className="insp-chain-box">
            <header>{node.root || node.kind === 'store' ? <ShieldCheck aria-hidden="true" /> : <TreeStructure aria-hidden="true" />}<span>{node.name}</span></header>
            <p>{role(node)}</p>
            {node.issuing && onOpenIssuer && (
              <button type="button" className="insp-link" onClick={onOpenIssuer}>{t('inspector.cert.inspectAuthority')}</button>
            )}
            {node.kind === 'store' && <span className="insp-chip"><Vault aria-hidden="true" />{t('inspector.cert.inTrustStore')}</span>}
            {node.cross && <span className="insp-chip"><LinkSimple aria-hidden="true" />{t('inspector.cert.crossCertified')}</span>}
          </section>,
          <div key={`link-${i}`} className="insp-connector" aria-hidden="true" />,
        ])}
        <section className="insp-chain-box is-selected">
          <header><Certificate aria-hidden="true" /><span>{name}</span></header>
          <p>{[cert.template_name, keyName].filter(Boolean).join(' · ') || '—'}</p>
          <StatusPill {...certificateState(cert, t)} />
        </section>
      </div>
      {sentence && (
        <p className={cn('insp-chain-note', `is-${sentence.tone}`)} data-testid="chain-status">
          {sentence.tone === 'warn' ? <Warning aria-hidden="true" /> : sentence.tone === 'good' ? <CheckCircle aria-hidden="true" /> : <LinkSimple aria-hidden="true" />}
          <span>
            {sentence.text}
            {chain.status === 'incomplete' && onAddToTrustStore && (
              <>{' '}<button type="button" className="insp-link" onClick={onAddToTrustStore}>{t('details.addIssuerToTrustStore')}</button></>
            )}
          </span>
        </p>
      )}
      <dl className="insp-props insp-chain-facts">
        <dt>{t('common.issuer')}</dt>
        <dd className="insp-mono">{cert.issuer || '—'}</dd>
        {cert.issuer_name && <><dt>{t('common.ca')}</dt><dd>{cert.issuer_name}</dd></>}
        {cert.caref && <><dt>{t('details.caReference')}</dt><dd className="insp-mono">{cert.caref}</dd></>}
      </dl>
    </>
  )
}
