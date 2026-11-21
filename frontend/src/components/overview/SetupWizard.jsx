/**
 * The mockup's setupWizard(): the first-run assistant at the top of the overview, three steps
 * (root, issuing CA, a protocol), each leading to the screen that does it; « Plus tard » folds it
 * into one line that keeps the progress. The steps and their state come from useSetup.
 */
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier'
import { useSetup } from '../shell/useSetup'
import { guardProps } from '../shell/health'

export function SetupWizard({ admin = false, share }) {
  const { t } = useTranslation()
  const setup = useSetup({ admin, share })
  if (!setup.visible) return null
  const { later, fold, steps, n, complete, next, nextIndex, nextTitle, doneText, savePref, guard, resumeRef, stepRef } = setup
  const count = n < 3
    ? <><strong>{t('shell.setup.count', { count: n })}</strong>{t('shell.setup.left', { count: 3 - n })}</>
    : <strong>{t('shell.setup.count', { count: n })}</strong>

  if (later) {
    return (
      <div className="setup-later" id="setup-later">
        <Icon name="settings" />
        <p>{t('shell.setup.laterLine')} {count}. {t('shell.setup.nextStep', { step: nextTitle })}</p>
        <button type="button" ref={resumeRef} className="btn" id="setup-resume" onClick={() => fold(false)}>{t('shell.setup.resume')}</button>
      </div>
    )
  }

  const suspended = guard.suspended ? { 'aria-disabled': 'true', 'aria-describedby': guard.noteId, onClick: (e) => e.preventDefault() } : {}
  return (
    <section className="panel setup-wizard" id="setup-wizard" aria-labelledby="setup-title">
      <header className="setup-head">
        <div>
          <h2 id="setup-title" tabIndex={-1}>{complete ? t('shell.setup.doneTitle') : t('shell.setup.title')}</h2>
          <p>{complete ? t('shell.setup.doneIntro') : t('shell.setup.intro')}</p>
        </div>
        {complete ? (
          <div className="setup-done-actions">
            <Link className="btn primary" id="setup-issue" to="/certificates?action=create" {...suspended}>
              <Icon name="plus" />{t('shell.setup.issueFirst')}
            </Link>
            <button type="button" className="btn quiet" id="setup-close" onClick={() => savePref('closed')}>{t('shell.setup.hide')}</button>
          </div>
        ) : (
          <button type="button" className="text-link" id="setup-later-btn" onClick={() => fold(true)}>{t('shell.setup.later')}</button>
        )}
      </header>
      <div className="setup-progress">
        <div className="setup-bar" role="progressbar" aria-labelledby="setup-count" aria-valuemin={0} aria-valuemax={3} aria-valuenow={n}>
          <span style={{ width: `${Math.round(n / 3 * 100)}%` }} />
        </div>
        <p id="setup-count">{count}</p>
      </div>
      <ol className="setup-steps">
        {steps.map((s, i) => {
          const blocked = !s.done && i > nextIndex
          const current = s === next
          const key = `shell.setup.steps.${s.id}`
          const cls = current ? 'btn primary' : 'btn'
          return (
            <li key={s.id} className={`setup-step ${s.done ? 'done' : blocked ? 'blocked' : 'todo'}`} id={`setup-step-${s.id}`}
              aria-current={current ? 'step' : undefined}>
              <span className="setup-num" aria-hidden="true">{s.done ? <Icon name="check" /> : i + 1}</span>
              <div className="setup-text">
                <h3>{i + 1}. {t(`${key}.title`)}</h3>
                <p>{s.done ? doneText(s.id) : t(`${key}.todo`)}</p>
              </div>
              <span className={`badge ${s.done ? 'good' : blocked ? '' : 'warn'} setup-state`}>
                <Icon name={s.done ? 'check' : blocked ? 'lock' : 'clock'} />
                {s.done ? t('shell.setup.stateDone') : blocked ? t('shell.setup.stateAfter', { step: nextIndex + 1 }) : t('shell.setup.stateTodo')}
              </span>
              {!s.done && (blocked || guard.suspended ? (
                <button type="button" ref={current ? stepRef : undefined} className={cls} id={`setup-go-${s.id}`} {...guardProps(guard, true)}>
                  {t(`${key}.action`)}
                </button>
              ) : (
                <Link ref={current ? stepRef : undefined} className={cls} id={`setup-go-${s.id}`} to={s.to}>{t(`${key}.action`)}</Link>
              ))}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
