/**
 * A CA enforcing a unique subject answers 409 when another entity's certificate carries it
 * (RFC 5280 §4.1.2.6). Manual issuance and CSR signing may then ask again with the override,
 * once the operator confirms; the server audits it.
 */
export const UNIQUE_SUBJECT_OVERRIDE = 'override_unique_subject'

/** The refusal's details ({ subject, serial_number }) when *error* is a taken subject, else null. */
export function takenSubject(error) {
  const details = error?.data?.details
  return error?.status === 409 && details?.override_field === UNIQUE_SUBJECT_OVERRIDE ? details : null
}

/**
 * Runs issue({}); on a taken subject asks the operator, then runs issue({ override_unique_subject: true }).
 * Resolves to null when the operator declines.
 */
export async function issueWithSubjectOverride(issue, showConfirm, t) {
  try {
    return await issue({})
  } catch (error) {
    const taken = takenSubject(error)
    if (!taken) throw error
    const confirmed = await showConfirm(
      t('certificates.subjectTakenConfirm', { subject: taken.subject, serial: taken.serial_number }),
      { title: t('certificates.subjectTakenTitle'), confirmText: t('certificates.issueAnyway'), variant: 'danger' })
    if (!confirmed) return null
    return issue({ [UNIQUE_SUBJECT_OVERRIDE]: true })
  }
}
