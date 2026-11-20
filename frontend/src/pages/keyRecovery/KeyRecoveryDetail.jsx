/**
 * Key recovery request in the inspector: heading (state, the actions the user
 * may take on it), then the Request and Log sections.
 */
import { useTranslation } from 'react-i18next'
import { Vault, Check, Prohibit, DownloadSimple } from '@phosphor-icons/react'
import { StatusPill } from '../../components/list'
import { WorkButton, WorkRecord, WorkRecords } from '../../components/work'
import { SectionTabs, tabId, panelId } from '../../components/inspector/InspectorTabs'
import { usePermission } from '../../hooks'
import { useOpenEntity } from '../../hooks/useOpenEntity'
import { keyRecoveryService } from '../../services'
import { formatDate } from '../../lib/utils'
import { recoveryRights, recoveryState } from './recoveryRules'
import { useRecoveryActions } from './useRecoveryActions'
import '../../components/work/work.css'

const when = (d) => formatDate(d, { time: true })

function Props({ rows }) {
  return (
    <dl className="ins-props">
      {rows.filter(Boolean).map(([k, v]) => <div key={k} style={{ display: 'contents' }}><dt>{k}</dt><dd>{v}</dd></div>)}
    </dl>
  )
}

export function KeyRecoveryDetail({ data: req, objectKey, title, section, onSection, onChanged }) {
  const { t } = useTranslation()
  const { hasPermission, username } = usePermission()
  const openEntity = useOpenEntity()
  // The list says whether dual control is on; a request opened from elsewhere assumes the default, on
  const rights = recoveryRights(req, { hasPermission, username, dualControl: req.dual_control !== false })
  const actions = useRecoveryActions({
    onDone: () => keyRecoveryService.get(req.id)
      .then((res) => { const row = res?.data || res; if (row?.id) onChanged?.({ ...row, dual_control: req.dual_control }) })
      .catch(() => {}),
  })
  const log = [
    { at: req.requested_at, label: t('keyRecovery.work.log.requested'), meta: [req.requested_by, req.reason].filter(Boolean).join(' · ') },
    req.decided_at && {
      at: req.decided_at,
      label: t(req.status === 'rejected' ? 'keyRecovery.work.log.rejected' : 'keyRecovery.work.log.approved'),
      meta: [req.decided_by, req.decision_note].filter(Boolean).join(' · '),
    },
    req.recovered_at && { at: req.recovered_at, label: t('keyRecovery.work.log.recovered'), meta: req.recovered_by },
  ].filter(Boolean).reverse()

  return (
    <>
      <header className="ins-heading">
        <div className="ins-title">
          <Vault className="ins-title-icon" aria-hidden="true" />
          <h2>{title}</h2>
          <StatusPill {...recoveryState(req, t)} />
        </div>
        <div className="ins-actions">
          {rights.approve && <WorkButton icon={Check} onClick={() => actions.open('approve', [req])}>{t('keyRecovery.work.approveAsk')}</WorkButton>}
          {rights.reject && <WorkButton quiet icon={Prohibit} onClick={() => actions.open('reject', [req])}>{t('keyRecovery.work.rejectAsk')}</WorkButton>}
          {rights.recover && <WorkButton primary icon={DownloadSimple} onClick={() => actions.open('recover', [req])}>{t('keyRecovery.work.recoverAsk')}</WorkButton>}
        </div>
      </header>
      <SectionTabs objectKey={objectKey} sections={['request', 'log']} current={section} onSelect={onSection}
        labelOf={(s) => t(`approvals.work.sections.${s}`)} />
      <div role="tabpanel" id={`${panelId(objectKey)}-section`} aria-labelledby={`${tabId(objectKey)}-${section}`}
        className="ins-panel" tabIndex={0}>
        {section === 'request' ? (
          <div className="wk-detail-grid">
            <section>
              <h3 className="ins-section-title">{t('approvals.work.detail.request')}</h3>
              <Props rows={[
                [t('approvals.work.detail.id'), <span className="ins-mono">#{req.id}</span>],
                [t('keyRecovery.work.certificate'), req.cert_id
                  ? <button type="button" className="ins-link" onClick={() => openEntity('certificate', req.cert_id)}>{title}</button> : title],
                [t('keyRecovery.reason'), req.reason],
                [t('approvals.requester'), req.requested_by],
                [t('approvals.work.detail.submitted'), when(req.requested_at)],
                [t('common.status'), <StatusPill {...recoveryState(req, t)} />],
              ]} />
            </section>
            {(req.decided_at || req.recovered_at) && (
              <section>
                <h3 className="ins-section-title">{t('approvals.work.detail.decision')}</h3>
                <Props rows={[
                  req.decided_by && [t('approvals.work.detail.by'), req.decided_by],
                  req.decided_at && [t('approvals.work.detail.on'), when(req.decided_at)],
                  req.decision_note && [t('keyRecovery.work.dialog.note'), req.decision_note],
                  req.recovered_by && [t('keyRecovery.work.recoveredBy'), req.recovered_by],
                  req.recovered_at && [t('keyRecovery.work.recoveredOn'), when(req.recovered_at)],
                ]} />
              </section>
            )}
          </div>
        ) : (
          <WorkRecords empty={t('approvals.work.log.none')}>
            {log.map((e, i) => <WorkRecord key={i} title={e.label} meta={e.meta} badge={<span className="wk-rl-meta">{when(e.at)}</span>} />)}
          </WorkRecords>
        )}
      </div>
      {actions.dialog}
    </>
  )
}

export default KeyRecoveryDetail
