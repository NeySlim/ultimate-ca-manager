/**
 * Which CAs a signing picker may offer: a revoked CA, one under a revoked
 * ancestor, one still waiting for its certificate or one taken offline
 * cannot sign, and the server refuses it at submission (review of #343).
 */
export const canSignNow = (ca) => !!ca
  && !ca.revoked && ca.status !== 'Revoked'
  && !ca.revoked_in_chain
  && !ca.pending && ca.status !== 'Pending'
  && !ca.offline

export const signingCas = (cas) => (cas || []).filter(canSignNow)
