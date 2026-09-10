/**
 * Which CAs a signing picker may offer: a revoked CA, one under a revoked
 * ancestor, one still waiting for its certificate, one taken offline or one
 * without a usable key cannot sign, and the server refuses it at submission
 * (review of #343, #348).
 */
export const canSignNow = (ca) => !!ca
  && !ca.revoked && ca.status !== 'Revoked'
  && !ca.revoked_in_chain
  && !ca.pending && ca.status !== 'Pending'
  && !ca.offline
  && (!!ca.has_private_key || !!ca.uses_hsm)

export const signingCas = (cas) => (cas || []).filter(canSignNow)

/**
 * The CAs a picker shows: those able to sign now, plus the one currently
 * selected when it no longer is, so a saved setting keeps showing its CA
 * instead of a blank field (the server re-judges the CA only when it changes).
 */
export const pickerCas = (cas, ...selected) => {
  const wanted = new Set(selected.filter(Boolean).map(String))
  const out = signingCas(cas)
  for (const ca of cas || []) {
    if (!out.includes(ca) && (wanted.has(String(ca.id)) || (ca.refid && wanted.has(String(ca.refid))))) out.push(ca)
  }
  return out
}

/**
 * Whether the "certificate only" state is worth a banner and a key import:
 * a CA created by signing an external request, or an intermediate held
 * without its key. A trust-store root imported on purpose without a key is
 * not one (#348).
 */
export const needsKeyImport = (ca) => !!ca?.certificate_only && !ca?.pending && !ca?.offline
  && (ca?.imported_from === 'csr_signed' || !!ca?.parent_id)
