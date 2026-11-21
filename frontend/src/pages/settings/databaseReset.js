/**
 * After a database reset every account is gone, this session with it. A generated
 * administrator password is announced (the command to read it, never the value)
 * and the page reloads only once that is acknowledged.
 */
export async function afterDatabaseReset(res, { t, showConfirm, showSuccess, reload }) {
  const result = res?.data || {}
  if (result.password_generated) {
    // In HA the file is on the node that ran the reset only
    const message = result.node
      ? t('messages.success.database.resetGeneratedOnNode', { command: result.read_command, node: result.node })
      : t('messages.success.database.resetGenerated', { command: result.read_command })
    await showConfirm(message, {
      title: t('settings.resetDatabase'),
      confirmText: t('common.ok'),
      cancelText: null,
    })
    reload()
    return
  }
  showSuccess(t('messages.success.database.reset'))
  setTimeout(reload, 2000)
}
