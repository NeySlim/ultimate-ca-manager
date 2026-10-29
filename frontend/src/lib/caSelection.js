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

/** How many CAs a signing picker leaves out, so it can say so instead of hiding them (#426). */
export const unlistedSigningCas = (cas) => (cas || []).length - signingCas(cas).length

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

/** How many CAs a picker built with pickerCas leaves out (#426). */
export const unlistedPickerCas = (cas, ...selected) => (cas || []).length - pickerCas(cas, ...selected).length

/** pickerCas for SCEP, which also refuses an HSM-backed CA: it cannot decrypt the request envelope. */
export const scepPickerCas = (cas, ...selected) => {
  const wanted = new Set(selected.filter(Boolean).map(String))
  return pickerCas(cas, ...selected).filter(ca =>
    !ca.uses_hsm || wanted.has(String(ca.id)) || (ca.refid && wanted.has(String(ca.refid))))
}

export const unlistedScepPickerCas = (cas, ...selected) => (cas || []).length - scepPickerCas(cas, ...selected).length

/** A CA held without its private key, a root imported on its own included: it cannot sign (#426). */
export const holdsNoKey = (ca) => !!ca?.certificate_only && !ca?.pending && !ca?.offline

/**
 * Whether the "certificate only" state is worth a banner and a key import:
 * a CA created by signing an external request, or an intermediate held
 * without its key. A trust-store root imported on purpose without a key is
 * not one (#348).
 */
export const needsKeyImport = (ca) => holdsNoKey(ca)
  && (ca?.imported_from === 'csr_signed' || ca?.is_root === false || ca?.type === 'intermediate')
