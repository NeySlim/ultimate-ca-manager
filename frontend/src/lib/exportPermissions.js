/**
 * Who may export a private key — one rule per entity type, taken from the API.
 *
 * A frontend guard is never a security boundary: the route decides, and it
 * already does. This predicate exists so a surface never offers a key export
 * the server will refuse with 403, and never hides one it would honour. Four
 * surfaces used to answer this question four different ways for the same
 * certificate; they now all ask here.
 *
 * The gates being mirrored, as of this writing:
 *
 *   certificate       POST /api/v2/certificates/<id>/export
 *                     backend/api/v2/certificates/export.py — read:private_keys
 *                     (an admin-only resource: no built-in role but Admin holds
 *                     it, so an Operator goes through Key Recovery instead)
 *
 *   ca                POST /api/v2/cas/<id>/export, and /offline in
 *                     file_exported mode: write:cas plus read:private_keys,
 *                     and 409 for a key that lives in an HSM
 *
 *   user_certificate  POST /api/v2/user-certificates/<id>/export
 *                     backend/api/v2/user_certificates.py — no key scope at
 *                     all. The route gates on ownership instead: a principal
 *                     who is neither admin, operator nor auditor only ever
 *                     sees and exports their own enrolment.
 *
 * Keep this table in step with those routes; the divergence it replaced was
 * born of each surface guessing.
 */

/**
 * @param {string} entityType - 'certificate' | 'ca' | 'user_certificate'
 * @param {object} ctx - from usePermission(), plus per-row facts
 * @param {(scope: string) => boolean} ctx.hasPermission
 * @param {(resource: string) => boolean} ctx.canWrite
 * @param {boolean} [ctx.usesHsm] - the CA's key is held in an HSM
 * @returns {boolean}
 */
export function canExportPrivateKey(entityType, ctx = {}) {
  const { hasPermission, canWrite, usesHsm = false } = ctx

  switch (entityType) {
    case 'certificate':
      return typeof hasPermission === 'function' && hasPermission('read:private_keys')

    case 'ca':
      return !usesHsm && typeof canWrite === 'function' && canWrite('cas')
        && typeof hasPermission === 'function' && hasPermission('read:private_keys')

    case 'user_certificate':
      return true

    default:
      // An unknown surface gets the safe answer rather than a guess.
      return false
  }
}
