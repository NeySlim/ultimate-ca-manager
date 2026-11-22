/** Figures the overview widgets draw: trends, success rates, compliance shares, folded sign-ins, CSV. */
import { describe, it, expect } from 'vitest'
import {
  seriesStats, issuedPerDay, recentTotal, failuresPerDay, successRate, rulePercent, ruleTone, gradeOfScore, foldActivity, toCsv,
} from '../overviewViz'

describe('seriesStats', () => {
  it('reads today, the gap with yesterday, the mean and the peak of a daily series', () => {
    const s = seriesStats([0, 2, 5, 1, 3])
    expect(s).toEqual({ sum: 11, today: 3, yesterday: 1, delta: 2, mean: 2.2, max: 5, maxIndex: 2 })
  })

  it('takes the latest peak when two days tie, and has no gap without a yesterday', () => {
    expect(seriesStats([4, 1, 4]).maxIndex).toBe(2)
    expect(seriesStats([7])).toMatchObject({ today: 7, yesterday: null, delta: null })
  })

  it('an empty series has nothing to say', () => {
    expect(seriesStats([])).toBeNull()
    expect(seriesStats(null)).toBeNull()
  })
})

describe('issuedPerDay', () => {
  it('sums the certificates issued by every CA, day by day', () => {
    const data = { days: 3, to: '2026-11-22', by_ca: [
      { caref: 'a', periods: [{ date: '2026-11-20', issued: 1, renewed: 4 }, { date: '2026-11-21', issued: 0 }, { date: '2026-11-22', issued: 2 }] },
      { caref: 'b', periods: [{ date: '2026-11-20', issued: 3 }, { date: '2026-11-21', issued: 1 }, { date: '2026-11-22', issued: 0 }] },
    ] }
    expect(issuedPerDay(data)).toEqual({ dates: ['2026-11-20', '2026-11-21', '2026-11-22'], values: [4, 1, 2] })
  })

  it('no CA issued anything: one zero per day of the window', () => {
    expect(issuedPerDay({ days: 3, to: '2026-11-01', by_ca: [] }))
      .toEqual({ dates: ['2026-10-30', '2026-10-31', '2026-11-01'], values: [0, 0, 0] })
  })

  it('a response without the per-CA series gives no curve, not a flat one', () => {
    expect(issuedPerDay({ total: 4 })).toBeNull()
    expect(issuedPerDay(null)).toBeNull()
  })
})

describe('recentTotal', () => {
  it('counts the issued and renewed of the last days of a longer window', () => {
    const periods = [{ issued: 9 }, { issued: 1, renewed: 2 }, { issued: 0, renewed: 1 }]
    expect(recentTotal({ total: 12, periods }, 2)).toBe(4)
  })

  it('without periods, the total the server gave', () => {
    expect(recentTotal({ total: 4, issued: 3 }, 7)).toBe(4)
  })
})

describe('failuresPerDay', () => {
  const day = (failed) => ({ date: 'd', ok: 1, failed })
  it('adds the protocol failures of each day over the last days asked', () => {
    const protocols = { acme: { periods: [day(1), day(0), day(2)] }, scep: { periods: [day(0), day(4), day(1)] }, est: { periods: null } }
    expect(failuresPerDay(protocols, ['acme', 'scep', 'est'], 2)).toEqual([4, 3])
  })

  it('no protocol with a series: no figure', () => {
    expect(failuresPerDay({ scheduler: { periods: null } }, ['acme'], 14)).toBeNull()
  })
})

describe('successRate', () => {
  it('is the share of successes, one decimal', () => {
    expect(successRate(121, 7)).toBe(94.5)
  })

  it('never reads 100 % while one operation failed', () => {
    expect(successRate(9999, 1)).toBe(99.9)
    expect(successRate(5, 0)).toBe(100)
  })

  it('has no rate without operations', () => {
    expect(successRate(0, 0)).toBeNull()
  })
})

describe('rulePercent and ruleTone', () => {
  it('gives the conforming share, rounded down while one certificate is in gap', () => {
    expect(rulePercent(189, 211)).toBe(10)
    expect(rulePercent(1, 1000)).toBe(99)
    expect(rulePercent(0, 211)).toBe(100)
  })

  it('has no share for an unknown count or an empty population', () => {
    expect(rulePercent(undefined, 10)).toBeNull()
    expect(rulePercent(3, 0)).toBeNull()
  })

  it('conforming, to watch (90 % and more), major gap below; a plain count stays information', () => {
    expect(ruleTone('rsa_below_3072', 0, 211)).toBe('good')
    expect(ruleTone('rsa_below_3072', 11, 211)).toBe('warn')
    expect(ruleTone('rsa_below_3072', 189, 211)).toBe('bad')
    expect(ruleTone('no_private_key', 189, 211)).toBe('info')
    expect(ruleTone('rsa_below_3072', undefined, 211)).toBe('')
  })
})

describe('gradeOfScore', () => {
  it.each([[100, 'A+'], [95, 'A+'], [94, 'A'], [85, 'A'], [78, 'B'], [55, 'C'], [40, 'D'], [39, 'F']])('%s reads %s', (score, grade) => {
    expect(gradeOfScore(score)).toBe(grade)
  })

  it('no score, no grade', () => {
    expect(gradeOfScore(null)).toBeNull()
  })
})

describe('foldActivity', () => {
  const at = (min) => new Date(Date.UTC(2026, 10, 22, 18, min)).toISOString()
  const login = (min, user = 'admin') => ({ action: 'login_success', user, timestamp: at(min), message: 'Logged in' })
  const op = (min) => ({ action: 'cert_created', user: 'admin', timestamp: at(min), message: 'made' })

  it('folds successive sign-ins of one user into one entry with their count and time span', () => {
    const items = foldActivity([login(53), login(50), login(41), login(37), login(30), op(20)])
    expect(items).toHaveLength(2)
    expect(items[0]).toMatchObject({ folded: true, count: 5, user: 'admin', action: 'login_success', last: at(53), first: at(30) })
    expect(items[1]).toMatchObject({ folded: false, entry: op(20) })
  })

  it('keeps apart the sign-ins of two users, an operation between them, and a lone sign-in', () => {
    const items = foldActivity([login(50), login(49, 'bob'), login(48, 'bob'), op(47), login(46)])
    expect(items.map((i) => (i.folded ? `${i.user}x${i.count}` : i.entry.action))).toEqual(['login_success', 'bobx2', 'cert_created', 'login_success'])
  })

  it('never folds a failed sign-in into the successes', () => {
    const failed = { action: 'login_failure', user: 'admin', timestamp: at(45) }
    expect(foldActivity([login(50), failed, login(40)]).every((i) => !i.folded)).toBe(true)
  })
})

describe('toCsv', () => {
  it('writes a header and one line per row, quoting what needs it', () => {
    expect(toCsv(['Day', 'Note'], [['2026-11-22', 'a, b'], ['x', 'say "hi"']]))
      .toBe('Day,Note\r\n2026-11-22,"a, b"\r\nx,"say ""hi"""\r\n')
  })

  it('defuses a text cell a spreadsheet would run as a formula, and keeps numbers', () => {
    expect(toCsv(['User'], [['=HYPERLINK("x")'], [-3], ['@cmd']])).toBe('User\r\n"\'=HYPERLINK(""x"")"\r\n-3\r\n\'@cmd\r\n')
  })
})
