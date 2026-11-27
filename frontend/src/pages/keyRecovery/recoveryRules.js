/**
 * Who may do what on a key recovery request, as the server decides it
 * (api/v2/key_recovery.py): an action the user would be refused is not offered.
 *  - approve: admin:key_recovery, and with dual control on, not on one's own request
 *  - reject: admin:key_recovery
 *  - recover: write:key_recovery, by the requester or an administrator of key recovery
 * The requester is the account id the request names; a request kept from before ids has none,
 * and then only its name holds an approval back.
 */
export const recoveryName = (r) => r.cert_cn || r.cert_refid || `#${r.cert_id}`

export const RECOVERY_TONES = { pending: 'warn', approved: 'good', rejected: 'bad', recovered: 'good', cancelled: 'muted' }

/** @param {{ hasPermission: Function, username: string, userId: number|null, dualControl: boolean }} who */
export function recoveryRights(req, { hasPermission, username, userId = null, dualControl }) {
  const admin = hasPermission('admin:key_recovery')
  const ownById = req?.requested_by_id != null && userId != null && req.requested_by_id === userId
  const ownByName = !!username && req?.requested_by === username
  const pending = req?.status === 'pending'
  return {
    approve: pending && admin && !(dualControl && (ownById || ownByName)),
    reject: pending && admin,
    recover: req?.status === 'approved' && hasPermission('write:key_recovery') && (ownById || admin),
  }
}

export function recoveryState(req, t) {
  const status = req?.status
  return {
    tone: RECOVERY_TONES[status] || 'muted',
    // An unknown state is shown as the server sent it
    label: RECOVERY_TONES[status] ? t(`keyRecovery.status.${status}`) : (status || ''),
  }
}

/** The two groups of the queue: requests to approve, then approved keys to recover. */
export function recoveryGroups(rows, t, dualControl) {
  return [
    { id: 'approve', label: t(dualControl ? 'keyRecovery.work.groups.approveOther' : 'keyRecovery.work.groups.approve'), icon: 'clock', tone: 'warn', status: 'pending' },
    { id: 'recover', label: t('keyRecovery.work.groups.recover'), icon: 'key', tone: '', status: 'approved' },
  ].map(({ status, ...g }) => ({ ...g, requests: rows.filter((r) => r.status === status) }))
}
