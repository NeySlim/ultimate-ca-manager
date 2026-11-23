/**
 * A key recovery request in the module dock. The mockup has no key recovery screen: the page
 * takes its work queue template, so the request opens in the queue's moduleInspector() dock as an
 * approval does (Demande, Journal), with the actions the user may take on it in the heading.
 */
import { useTranslation } from 'react-i18next'
import { Btn, Dock, DockBody, Facts, Pill, RecordList, RecordRow, Section } from '../../components/atelier'
import { fact } from '../../components/atelier/facts'
import { usePermission } from '../../hooks'
import { useOpenEntity } from '../../hooks/useOpenEntity'
import { formatDate } from '../../lib/utils'
import { recoveryRights, recoveryState, recoveryName } from './recoveryRules'

const when = (d) => formatDate(d, { time: true })

/** The row's (and the dock's) buttons; `slot` keeps Approuver…'s place where the user may not approve. */
export function RecoveryButtons({ req, who, onAsk, disabled, slot = false, named = true }) {
  const { t } = useTranslation()
  const rights = recoveryRights(req, who)
  const name = recoveryName(req)
  const aria = (key) => (named ? t(key, { name }) : undefined)
  return (
    <>
      {rights.approve ? (
        <Btn icon="check" write disabled={disabled || undefined} onClick={() => onAsk('approve')}
          aria-label={aria('keyRecovery.work.approveNamed')}>{t('keyRecovery.work.approveAsk')}</Btn>
      ) : slot && (
        <span className="btn slot" aria-hidden="true">{t('keyRecovery.work.approveAsk')}</span>
      )}
      {rights.reject && (
        <Btn tone="quiet" icon="block" write disabled={disabled || undefined} onClick={() => onAsk('reject')}
          aria-label={aria('keyRecovery.work.rejectNamed')}>{t('keyRecovery.work.rejectAsk')}</Btn>
      )}
      {rights.recover && (
        <Btn icon="download" write disabled={disabled || undefined} onClick={() => onAsk('recover')}
          aria-label={aria('keyRecovery.work.recoverNamed')}>{t('keyRecovery.work.recoverAsk')}</Btn>
      )}
    </>
  )
}

export function RecoveryPanel({ req }) {
  const { t } = useTranslation()
  const openEntity = useOpenEntity()
  const state = recoveryState(req, t)
  const title = recoveryName(req)
  return (
    <div className="module-detail">
      <Section title={t('approvals.work.detail.request')}>
        <Facts items={[
          [t('approvals.work.detail.id'), <span className="mono">#{req.id}</span>],
          [t('keyRecovery.work.certificate'), req.cert_id
            ? <button type="button" className="text-link" onClick={() => openEntity('certificate', req.cert_id)}>{title}</button> : title],
          fact(t('approvals.requester'), req.requested_by),
          fact(t('approvals.work.detail.submitted'), req.requested_at && when(req.requested_at)),
          { label: t('approvals.work.detail.state'), state: [state.tone, state.label] },
          { ...fact(t('keyRecovery.reason'), req.reason), long: true },
        ]} />
      </Section>
      {(req.decided_at || req.recovered_at) && (
        <Section title={t('approvals.work.detail.decision')}>
          <Facts items={[
            req.decided_by && [t('approvals.work.detail.by'), req.decided_by],
            req.decided_at && [t('approvals.work.detail.on'), when(req.decided_at)],
            req.decision_note && { label: t('keyRecovery.work.dialog.note'), value: req.decision_note, long: true },
            req.recovered_by && [t('keyRecovery.work.recoveredBy'), req.recovered_by],
            req.recovered_at && [t('keyRecovery.work.recoveredOn'), when(req.recovered_at)],
          ]} />
        </Section>
      )}
    </div>
  )
}

/** The mockup's journal(): what happened, its detail under it, who and when on the right. */
export function RecoveryLog({ req }) {
  const { t } = useTranslation()
  const log = [
    { at: req.requested_at, label: t('keyRecovery.work.log.requested'), meta: req.reason, actor: req.requested_by },
    req.decided_at && {
      at: req.decided_at,
      label: t(req.status === 'rejected' ? 'keyRecovery.work.log.rejected' : 'keyRecovery.work.log.approved'),
      meta: req.decision_note || t('approvals.work.log.noReason'),
      actor: req.decided_by,
    },
    req.recovered_at && { at: req.recovered_at, label: t('keyRecovery.work.log.recovered'), meta: '', actor: req.recovered_by },
  ].filter(Boolean).reverse()
  return (
    <RecordList empty={t('approvals.work.log.none')}>
      {log.map((e, i) => (
        <RecordRow key={i} title={e.label} meta={e.meta || undefined}
          badge={<span className="rl-meta">{[e.actor, when(e.at)].filter(Boolean).join(' · ')}</span>} />
      ))}
    </RecordList>
  )
}

/** The dock of the open request; onAsk(kind) opens the decision or the recovery. */
export function KeyRecoveryDock({ req, section, onSection, onClose, onAsk }) {
  const { t } = useTranslation()
  const { hasPermission, username } = usePermission()
  const title = recoveryName(req)
  const state = recoveryState(req, t)
  // The list says whether dual control is on; a request read alone assumes the default, on
  const who = { hasPermission, username, dualControl: req.dual_control !== false }
  return (
    <Dock label={t('atelier.detailOf', { name: t('keyRecovery.title') })} tabsLabel={t('atelier.openItem')} activeKey={req.id}
      tabs={[{ key: req.id, title, icon: 'key' }]} onClose={onClose}>
      <DockBody icon="key" title={title} badge={<Pill label={state.label} tone={state.tone} />}
        actions={<RecoveryButtons req={req} who={who} onAsk={onAsk} />}
        sections={[['request', t('approvals.work.sections.request')], ['log', t('approvals.work.sections.log')]]}
        section={section} onSection={onSection} sectionsLabel={t('atelier.sectionsOf', { name: title })}>
        {section === 'log' ? <RecoveryLog req={req} /> : <RecoveryPanel req={req} />}
      </DockBody>
    </Dock>
  )
}
