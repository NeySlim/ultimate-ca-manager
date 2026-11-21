import { describe, expect, it } from 'vitest'
import { ceilingNotice } from '../backupCeiling'

const t = (key, opts) => `${key} ${JSON.stringify(opts)}`
const schedule = { max_total_mb: 64, min_keep: 3 }

describe('ceilingNotice', () => {
  it('is silent when the server sent no warning', () => {
    expect(ceilingNotice({ removed: 2, warning: null }, schedule, {}, t)).toBeNull()
    expect(ceilingNotice({ filename: 'a.ucmbkp' }, schedule, {}, t)).toBeNull()
  })

  it('after a creation, says the next retention removes the oldest', () => {
    expect(ceilingNotice({ warning: 'over' }, schedule, {}, t))
      .toBe('settings.backupOverCeiling {"ceiling":64}')
  })

  it('after a retention, names what is kept on disk', () => {
    expect(ceilingNotice({ warning: 'over' }, schedule, { afterRetention: true }, t))
      .toBe('settings.backupOverCeilingKept {"minKeep":3}')
  })

  it('after a retention in HA, names what the database keeps', () => {
    expect(ceilingNotice({ warning: 'over' }, schedule, { afterRetention: true, shared: true }, t))
      .toBe('settings.backupOverCeilingKeptShared {"minKeep":3}')
  })
})
