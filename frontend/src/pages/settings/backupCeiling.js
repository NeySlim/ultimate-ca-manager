// The ceiling notice after a creation or a retention: shown only when the server sent
// `warning`, worded from the saved schedule, never from the field being typed.
export function ceilingNotice(outcome, schedule = {}, { afterRetention = false, shared = false } = {}, t) {
  if (!outcome?.warning) return null
  if (afterRetention) {
    return t(shared ? 'settings.backupOverCeilingKeptShared' : 'settings.backupOverCeilingKept',
      { minKeep: schedule.min_keep ?? 2 })
  }
  return t('settings.backupOverCeiling', { ceiling: schedule.max_total_mb ?? 0 })
}
