/**
 * State of the first-run steps (root CA, issuing CA, a protocol), shared by the card of the shell
 * and the overview's assistant: shown to an administrator of an instance without any CA nor
 * certificate, then until its steps are done; closed or finished, never again.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { acmeService, casService, dashboardService, estService, scepService } from '../../services'
import { getPreferences, persistPreference, subscribePreferences } from '../../stores/userPreferencesStore'
import { certificateKeyLabel } from '../../lib/certificateDetail'
import { useWriteGuard } from './health'

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
const caName = (ca) => ca?.common_name || ca?.descr || ca?.name || ''

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
  const rootCa = list.find(c => c.is_root)
  const issuingCa = list.find(c => !c.is_root)
  const protocolName = ok(acme) ? 'ACME' : ok(scep) ? 'SCEP' : ok(est) ? 'EST' : null
  return {
    certificates,
    cas: list.length,
    root: !!rootCa,
    issuing: !!issuingCa,
    protocol: !!protocolName,
    // What exists, for the summary of a step done
    rootCa, issuingCa, protocolName,
  }
}

/** The state of the first-run steps, shared by the card of the shell and the overview's assistant. */
export function useSetup({ admin = false, share }) {
  const { t, i18n } = useTranslation()
  const guard = useWriteGuard()
  const [pref, savePref] = useSetupPreference()
  const [state, setState] = useState(null)
  const [later, setLater] = useState(() => readLocal(LATER_KEY, sessionStorage) === '1')
  // Where the focus goes once the card is folded or unfolded: Resume, or the current step's button
  const [focusTo, setFocusTo] = useState(null)
  const resumeRef = useRef(null)
  const stepRef = useRef(null)
  useEffect(() => {
    if (!focusTo) return
    ;(focusTo === 'resume' ? resumeRef : stepRef).current?.focus()
    setFocusTo(null)
  }, [focusTo])
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

  const visible = admin && eligible && pref !== 'closed' && !(pref === 'done' && !complete)
  if (!visible) return { visible: false }

  const next = steps.find(s => !s.done)
  const nextIndex = steps.indexOf(next)
  const fold = (value) => {
    writeLocal(LATER_KEY, value ? '1' : '0', sessionStorage)
    setLater(value)
    setFocusTo(value ? 'resume' : 'step')
  }
  // A step done says what exists, as the mockup does; a fixed sentence when the API names nothing
  const doneText = (id) => {
    const what = (ca) => [caName(ca), certificateKeyLabel(ca, t)].filter(Boolean).join(', ')
    if (id === 'root' && caName(state.rootCa)) return t('shell.setup.doneWhat', { what: what(state.rootCa) })
    if (id === 'issuing' && caName(state.issuingCa)) {
      return caName(state.rootCa)
        ? t('shell.setup.steps.issuing.doneWith', { what: what(state.issuingCa), root: caName(state.rootCa) })
        : t('shell.setup.doneWhat', { what: what(state.issuingCa) })
    }
    if (id === 'protocol' && state.protocolName) return t('shell.setup.steps.protocol.doneWith', { protocol: state.protocolName })
    return t(`shell.setup.steps.${id}.done`)
  }
  const nextTitle = lowerFirst(t(`shell.setup.steps.${next?.id || 'root'}.title`), i18n?.language)
  return { visible: true, later: later && !complete, fold, steps, n, complete, next, nextIndex, nextTitle, doneText, savePref, guard, resumeRef, stepRef }
}
