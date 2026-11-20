/**
 * First run: the "Initial setup" card, three steps (root CA, issuing CA, a protocol), each
 * leading to the screen that does it. Shown to an administrator of an instance without any
 * CA nor certificate, then until its steps are done; closed or finished, never again.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Check, Clock, Gear, Lock, Plus } from '@phosphor-icons/react'
import { acmeService, casService, dashboardService, estService, scepService } from '../../services'
import { getPreferences, persistPreference, subscribePreferences } from '../../stores/userPreferencesStore'
import { guardProps, useWriteGuard } from './health'

export const SETUP_PREF = 'setup_card'
// The server keeps only the preference keys it knows: a copy in this browser keeps "closed" until it does
const LOCAL_KEY = 'ucm-setup-card'
const LATER_KEY = 'ucm-setup-later'
const FINAL = ['closed', 'done']
// A title inside a sentence: first letter only, so acronyms (AC, CA) keep their case; German nouns keep theirs
const lowerFirst = (text, lang) => (/^de/.test(lang || '') ? text : text.charAt(0).toLocaleLowerCase() + text.slice(1))

const readLocal = (key, store = localStorage) => { try { return store.getItem(key) } catch { return null } }
const writeLocal = (key, value, store = localStorage) => { try { store.setItem(key, value) } catch { /* optional */ } }

function useSetupPreference() {
  const [value, setValue] = useState(() => getPreferences()[SETUP_PREF] || readLocal(LOCAL_KEY))
  useEffect(() => subscribePreferences(p => setValue(p[SETUP_PREF] || readLocal(LOCAL_KEY))), [])
  const save = (next) => {
    writeLocal(LOCAL_KEY, next)
    setValue(next)
    persistPreference(SETUP_PREF, next)
  }
  return [value, save]
}

const listOf = (res) => {
  const d = res?.data ?? res
  return Array.isArray(d) ? d : Array.isArray(d?.items) ? d.items : []
}
const usable = (res) => { const d = res?.data ?? res; return !!d?.enabled && !!(d.issuing_ca_id || d.ca_id) }

/**
 * What the instance holds, null while unknown. The counts come first, from the overview's own
 * read when the page shares it; the CA list and the protocols are asked only of an empty instance.
 */
async function readState(share) {
  const read = (key, run) => (share ? share(key, run) : run())
  const counts = (await read('stats', () => dashboardService.getStats()))?.data
  if (!counts) return null
  const certificates = Number(counts.total_certificates) || 0
  if (certificates > 0) return { certificates }
  const [cas, acme, scep, est] = await Promise.allSettled([
    casService.getAll(), acmeService.getSettings(), scepService.getConfig(), estService.getConfig(),
  ])
  if (cas.status !== 'fulfilled') return null
  const list = listOf(cas.value)
  const ok = (r) => r.status === 'fulfilled' && usable(r.value)
  return {
    certificates,
    cas: list.length,
    root: list.some(c => c.is_root),
    issuing: list.some(c => !c.is_root),
    protocol: ok(acme) || ok(scep) || ok(est),
  }
}

/**
 * admin: the page's own answer to "is this user an administrator" (the steps need every right);
 * share: the overview's (key, run) to read the counts with its figures strip, in one request.
 */
export function SetupCard({ admin = false, share }) {
  const { t, i18n } = useTranslation()
  const guard = useWriteGuard()
  const [pref, savePref] = useSetupPreference()
  const [state, setState] = useState(null)
  const [later, setLater] = useState(() => readLocal(LATER_KEY, sessionStorage) === '1')
  const final = FINAL.includes(pref)

  useEffect(() => {
    if (!admin || final) return undefined
    let alive = true
    readState(share).then(s => { if (alive) setState(s) }).catch(() => {})
    return () => { alive = false }
  }, [admin, final]) // eslint-disable-line react-hooks/exhaustive-deps

  // 'done' here means finished during this visit: the state was read before it was written
  const eligible = !!state && state.certificates === 0 && (state.cas === 0 || pref === 'started' || pref === 'done')
  const steps = state ? [
    { id: 'root', done: state.root, to: '/cas?action=create' },
    { id: 'issuing', done: state.issuing, to: '/cas?action=create' },
    { id: 'protocol', done: state.protocol, to: '/acme?tab=config' },
  ] : []
  const n = steps.filter(s => s.done).length
  const complete = steps.length > 0 && n === steps.length

  // Started on an empty instance, the card follows its steps; finished, it is shown this time only
  useEffect(() => {
    if (!eligible || final) return
    if (complete) savePref('done')
    else if (pref !== 'started') savePref('started')
  }, [eligible, complete, final, pref]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!admin || !eligible || pref === 'closed') return null
  if (pref === 'done' && !complete) return null

  const next = steps.find(s => !s.done)
  const nextIndex = steps.indexOf(next)
  const count = n < 3
    ? <><strong>{t('shell.setup.count', { count: n })}</strong>{t('shell.setup.left', { count: 3 - n })}</>
    : <strong>{t('shell.setup.count', { count: n })}</strong>
  const fold = (value) => { writeLocal(LATER_KEY, value ? '1' : '0', sessionStorage); setLater(value) }

  if (later && !complete) {
    return (
      <div className="shell-setup-later" id="shell-setup-later">
        <Gear size={16} aria-hidden="true" />
        <p>{t('shell.setup.laterLine')} {count}. {t('shell.setup.nextStep', { step: lowerFirst(t(`shell.setup.steps.${next.id}.title`), i18n?.language) })}</p>
        <button type="button" className="shell-btn" onClick={() => fold(false)}>{t('shell.setup.resume')}</button>
        <button type="button" className="shell-btn is-quiet" onClick={() => savePref('closed')}>{t('shell.setup.hide')}</button>
      </div>
    )
  }

  return (
    <section className="shell-setup" id="shell-setup" aria-labelledby="shell-setup-title">
      <header className="shell-setup-head">
        <div>
          <h2 id="shell-setup-title" tabIndex={-1}>{complete ? t('shell.setup.doneTitle') : t('shell.setup.title')}</h2>
          <p>{complete ? t('shell.setup.doneIntro') : t('shell.setup.intro')}</p>
        </div>
        {complete ? (
          <div className="shell-setup-done-actions">
            <Link className="shell-btn is-primary" to="/certificates?action=create" {...(guard.suspended ? { 'aria-disabled': 'true', 'aria-describedby': guard.noteId, onClick: (e) => e.preventDefault() } : {})}>
              <Plus size={16} aria-hidden="true" />{t('shell.setup.issueFirst')}
            </Link>
            <button type="button" className="shell-btn is-quiet" onClick={() => savePref('closed')}>{t('shell.setup.hide')}</button>
          </div>
        ) : (
          <button type="button" className="shell-text-link" onClick={() => fold(true)}>{t('shell.setup.later')}</button>
        )}
      </header>
      <div className="shell-setup-progress">
        <div className="shell-setup-bar" role="progressbar" aria-labelledby="shell-setup-count" aria-valuemin={0} aria-valuemax={3} aria-valuenow={n}>
          <span style={{ width: `${Math.round(n / 3 * 100)}%` }} />
        </div>
        <p id="shell-setup-count">{count}</p>
      </div>
      <ol className="shell-setup-steps">
        {steps.map((s, i) => {
          const blocked = !s.done && i > nextIndex
          const current = s === next
          const key = `shell.setup.steps.${s.id}`
          return (
            <li key={s.id} className={`shell-setup-step ${s.done ? 'is-done' : blocked ? 'is-blocked' : 'is-todo'}`} aria-current={current ? 'step' : undefined}>
              <span className="shell-setup-num" aria-hidden="true">{s.done ? <Check size={14} /> : i + 1}</span>
              <div className="shell-setup-text">
                <h3>{i + 1}. {t(`${key}.title`)}</h3>
                <p>{s.done ? t(`${key}.done`) : t(`${key}.todo`)}</p>
              </div>
              <span className={`shell-setup-state${s.done ? ' is-good' : blocked ? '' : ' is-warn'}`}>
                {s.done ? <Check size={14} aria-hidden="true" /> : blocked ? <Lock size={14} aria-hidden="true" /> : <Clock size={14} aria-hidden="true" />}
                {s.done ? t('shell.setup.stateDone') : blocked ? t('shell.setup.stateAfter', { step: nextIndex + 1 }) : t('shell.setup.stateTodo')}
              </span>
              {!s.done && (blocked || guard.suspended ? (
                <button type="button" className={`shell-btn${current ? ' is-primary' : ''}`} {...guardProps(guard, true)}>
                  {t(`${key}.action`)}
                </button>
              ) : (
                <Link className={`shell-btn${current ? ' is-primary' : ''}`} to={s.to}>{t(`${key}.action`)}</Link>
              ))}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
