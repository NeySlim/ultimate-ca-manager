import { extractCN } from '../../../lib/utils'

/**
 * The authorities above a certificate, root first, from the chain the server validated
 * (it lists the issuing authority first). Without any, the issuer named by the certificate.
 */
export function chainPath(cert) {
  const status = cert?.chain_status?.status
  const links = cert?.chain_status?.chain || []
  const path = links.map((link, i) => ({
    name: link.name,
    kind: link.type === 'trust_store' ? 'store' : 'managed',
    issuing: i === 0 && !!cert.caref,
    cross: link.cross_certificate_id != null,
  })).reverse()
  const complete = status === 'complete'
  path.forEach((node, i) => {
    node.root = complete && i === 0
    node.level = complete ? i + 1 : null
  })
  const selfSigned = !!cert?.subject && cert.subject === cert.issuer
  if (!path.length && !selfSigned) {
    const name = extractCN(cert?.issuer) || cert?.issuer_name
    if (name) path.push({ name, kind: 'unknown', issuing: false, cross: false, root: false, level: null })
  }
  return { path, status: status || 'unknown', selfSigned, anchor: cert?.chain_status?.trust_anchor || null, source: cert?.chain_status?.trust_source || null }
}

/** What the server says of the chain, in one sentence, with the tone of its mark. */
export function chainSentence(chain, t) {
  if (chain.selfSigned && !chain.path.length) return { tone: 'muted', text: t('inspector.cert.selfSigned') }
  if (chain.status === 'complete') {
    return {
      tone: 'good',
      text: t(chain.source === 'trust_store' ? 'inspector.cert.chainToStore' : 'inspector.cert.chainToRoot', { anchor: chain.anchor || '' }),
    }
  }
  if (chain.status === 'partial') return { tone: 'muted', text: t('inspector.cert.chainPartial') }
  if (chain.status === 'incomplete') return { tone: 'warn', text: t('details.chainIncompleteHint') }
  return null
}
