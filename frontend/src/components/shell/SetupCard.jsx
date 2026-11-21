/**
 * First run: the "Initial setup" card, three steps (root CA, issuing CA, a protocol), each
 * leading to the screen that does it. Shown to an administrator of an instance without any
 * CA nor certificate, then until its steps are done; closed or finished, never again.
 */
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Check, Clock, Gear, Lock, Plus } from '@phosphor-icons/react'
import { guardProps } from './health'
import { useSetup } from './useSetup'

export { SETUP_PREF } from './useSetup'

/**
 * admin: the page's own answer to "is this user an administrator" (the steps need every right);
 * share: the overview's (key, run) to read the counts with its figures strip, in one request.
 */
export function SetupCard({ admin = false, share }) {
  const { t } = useTranslation()
  const setup = useSetup({ admin, share })
  if (!setup.visible) return null
  const { later, fold, steps, n, complete, next, nextIndex, nextTitle, doneText, savePref, guard, resumeRef, stepRef } = setup
  const count = n < 3
    ? <><strong>{t('shell.setup.count', { count: n })}</strong>{t('shell.setup.left', { count: 3 - n })}</>
    : <strong>{t('shell.setup.count', { count: n })}</strong>

  if (later) {
    return (
      <div className="shell-setup-later" id="shell-setup-later">
        <Gear size={16} aria-hidden="true" />
        <p>{t('shell.setup.laterLine')} {count}. {t('shell.setup.nextStep', { step: nextTitle })}</p>
        <button type="button" ref={resumeRef} className="shell-btn" onClick={() => fold(false)}>{t('shell.setup.resume')}</button>
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
              <span className="shell-setup-num" aria-hidden="true">{s.done ? <Check size={13} /> : i + 1}</span>
              <div className="shell-setup-text">
                <h3>{i + 1}. {t(`${key}.title`)}</h3>
                <p>{s.done ? doneText(s.id) : t(`${key}.todo`)}</p>
              </div>
              <span className={`shell-setup-state${s.done ? ' is-good' : blocked ? '' : ' is-warn'}`}>
                {s.done ? <Check size={13} aria-hidden="true" /> : blocked ? <Lock size={13} aria-hidden="true" /> : <Clock size={13} aria-hidden="true" />}
                {s.done ? t('shell.setup.stateDone') : blocked ? t('shell.setup.stateAfter', { step: nextIndex + 1 }) : t('shell.setup.stateTodo')}
              </span>
              {!s.done && (blocked || guard.suspended ? (
                <button type="button" ref={current ? stepRef : undefined} className={`shell-btn${current ? ' is-primary' : ''}`} {...guardProps(guard, true)}>
                  {t(`${key}.action`)}
                </button>
              ) : (
                <Link ref={current ? stepRef : undefined} className={`shell-btn${current ? ' is-primary' : ''}`} to={s.to}>{t(`${key}.action`)}</Link>
              ))}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
