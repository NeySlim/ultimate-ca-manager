import { casService, certificatesService } from '../services'

// Helpers for cross-certificates (#400)

// The CN of an RFC 4514 distinguished name, or the whole name when it has none
export function commonNameOf(dn) {
  if (!dn) return ''
  const match = /(?:^|,)\s*CN=((?:\\.|[^,])+)/i.exec(dn)
  return match ? match[1].replace(/\\(.)/g, '$1').trim() : dn
}

// A certificate file as PEM text: PEM stays as read, DER is wrapped
export async function certificateFileToPem(file) {
  const bytes = new Uint8Array(await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(reader.error)
    reader.readAsArrayBuffer(file)
  }))
  const text = new TextDecoder('utf-8', { fatal: false }).decode(bytes)
  if (text.includes('-----BEGIN')) return text
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  const lines = btoa(binary).match(/.{1,64}/g) || []
  return `-----BEGIN CERTIFICATE-----\n${lines.join('\n')}\n-----END CERTIFICATE-----\n`
}

// Why a cross-certificate is not servable, or null
export function crossStateOf(row) {
  if (row.revoked) return 'revoked'
  if (row.expired) return 'expired'
  if (row.not_yet_valid) return 'notYetValid'
  return null
}

// The import answered 409 and a cross-certificate can be attached instead
export function crossAttachOffered(err) {
  const details = err?.data?.details
  return err?.status === 409 && details?.code === 'cross_certificate_detected'
    && (details.options || []).includes('attach')
}

// The 409 offers to replace the CA's current certificate
export function crossReplaceOffered(err) {
  const details = err?.data?.details
  return err?.status === 409 && details?.code === 'cross_certificate_detected'
    && (details.options || []).includes('replace')
}

// The chains a CA or certificate can present, [] when it has no choice or the lookup fails
export async function fetchChainVariants({ type, id }) {
  try {
    const res = type === 'ca' ? await casService.getChainVariants(id) : await certificatesService.getById(id)
    const data = res?.data ?? res
    const variants = type === 'ca' ? data : data?.chain_status?.variants
    return Array.isArray(variants) ? variants : []
  } catch {
    return []
  }
}
