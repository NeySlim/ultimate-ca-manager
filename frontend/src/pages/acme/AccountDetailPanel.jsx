/**
 * The dock of an ACME account, the mockup's acmeAccountPanel() and its tabs (Compte, Commandes,
 * Défis), on the server's account, orders and challenges. The client name, the EAB binding, the
 * failure of a challenge and the account journal are functions the product lacks (M01, M02);
 * a contact e-mail to edit and the removal of an account are the product's own.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Dock, DockBody, Section, Props, RecordList, RecordRow, Pill, TextLink, AtelierDialog, Icon } from '../../components/atelier'
import { apiClient } from '../../services'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { stateLabel } from '../../lib/stateLabel'
import { dateOf, dateTimeOf } from '../admin/adminDates'
import { Copyable, Notice } from '../protocols/atelierParts'
import { ACCOUNT_TONES, accountLabel, accountContact } from '../protocols/protocolStates'

const ORDER_TONES = { valid: 'good', ready: 'good', issued: 'good', pending: 'warn', processing: 'warn', invalid: 'bad' }


/** The URL or record a challenge of this type is checked at (RFC 8555 §8.3, §8.4; RFC 8737). */
function challengeWhere(t, ch) {
  const type = String(ch.type || '').toUpperCase()
  if (type.startsWith('DNS')) return t('acme.challengeTxt', { name: `_acme-challenge.${ch.domain}` })
  if (type === 'HTTP-01') return `http://${ch.domain}/.well-known/acme-challenge/`
  if (type === 'TLS-ALPN-01') return t('acme.challengeAlpn', { host: `${ch.domain}:443` })
  return ch.domain
}

export default function AccountDock({ account, orders = [], challenges = [], section, onSection, onClose, onDeactivate, onDelete, onChanged }) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const { showSuccess, showError } = useNotification()
  const { hasPermission } = usePermission()
  const canWrite = hasPermission('write:acme')
  const canDelete = hasPermission('delete:acme')
  const [editing, setEditing] = useState(false)
  const [emailDraft, setEmailDraft] = useState('')
  const [confirming, setConfirming] = useState(false)
  const currentEmail = accountContact(account)
  const name = accountLabel(account)
  const pill = (s) => <Pill label={t(`acme.accountState.${s}`, { defaultValue: stateLabel(t, s) })} tone={ACCOUNT_TONES[s] || 'muted'} />
  const orderPill = (o) => <Pill label={stateLabel(t, o.status)} tone={ORDER_TONES[String(o.status).toLowerCase()] || 'muted'} />
  const last = orders[0]
  const failing = orders.filter((o) => String(o.status).toLowerCase() === 'invalid').length

  const saveEmail = async () => {
    try {
      const response = await apiClient.patch(`/acme/accounts/${account.account_id || account.id}`, { email: emailDraft.trim() })
      const contact = response?.data?.contact ?? (emailDraft.trim() ? [`mailto:${emailDraft.trim()}`] : [])
      onChanged?.({ ...account, contact })
      showSuccess(t('acme.emailUpdated'))
      setEditing(false)
    } catch (err) {
      showError(err.message || t('messages.errors.updateFailed.settings'))
    }
  }

  return (
    <Dock label={t('atelier.detailOf', { name: 'ACME' })} tabsLabel={t('atelier.openItem')} activeKey={account.id}
      tabs={[{ key: account.id, title: name, icon: 'refresh' }]} onClose={onClose}>
      <DockBody icon="refresh" title={name} badge={pill(account.status)} section={section} onSection={onSection}
        sectionsLabel={t('atelier.sectionsOf', { name })}
        sections={[['account', t('acme.tabs.account')], ['orders', t('acme.orders')], ['challenges', t('common.challenges')]]}
        actions={<>
          {canWrite && account.status === 'valid' && (
            <Btn tone="danger" icon="block" id="acme-disable" onClick={() => setConfirming(true)}>{t('acme.disableAccount')}</Btn>
          )}
          {canDelete && <Btn icon="close" id="acme-delete" onClick={() => onDelete(account.id)}>{t('common.delete')}</Btn>}
        </>}>
        {section === 'account' && (
          <div className="module-detail">
            <Section title={t('acme.tabs.account')}>
              <Props items={[
                [t('acme.identifier'), <Copyable key="id" value={account.account_id} label={t('acme.accountId')} />],
                [t('acme.contact'), (
                  <>{currentEmail ? `mailto:${currentEmail}` : t('acme.noContact')}
                    {canWrite && <>{' '}<TextLink id="acme-edit-email" onClick={() => { setEmailDraft(currentEmail); setEditing(true) }}>{t('acme.editEmail')}</TextLink></>}
                  </>
                )],
                [t('acme.accountKey'), account.key_type || '—'],
                [t('acme.createdOn'), dateOf(account.created_at, locale) || '—'],
                [t('acme.termsOfService'), t(account.terms_of_service_agreed || account.tos_agreed ? 'acme.accepted' : 'acme.notAccepted')],
              ]} />
            </Section>
            <Section title={t('atelier.state')}>
              <Props items={[
                [t('atelier.state'), pill(account.status)],
                [t('acme.orders'), failing ? t('acme.ordersFailing', { count: orders.length, failing }) : String(orders.length)],
                [t('acme.lastOrder'), last ? (
                  <>{t('acme.orderLine', { id: String(last.order_id || last.id).slice(0, 12) })} · <span className={ORDER_TONES[String(last.status).toLowerCase()] || 'muted'}>{stateLabel(t, last.status)}</span><br />
                    <span className="muted">{last.domain}, {dateTimeOf(last.created_at, locale)}</span></>
                ) : t('acme.noneOrder')],
              ]} />
              {account.status !== 'valid' && <Notice>{t('acme.deactivationFinal')}</Notice>}
            </Section>
          </div>
        )}
        {section === 'orders' && (
          <RecordList empty={t('acme.noCertificateOrders')}>
            {orders.map((o, i) => (
              <RecordRow key={o.id ?? i} title={`${t('acme.orderLine', { id: String(o.order_id || o.id).slice(0, 12) })} · ${o.domain || o.identifier || t('common.unknown')}`}
                meta={[o.method, o.created_at && dateTimeOf(o.created_at, locale), o.source === 'proxy' && t('acme.proxy')].filter(Boolean).join(' · ')}
                badge={orderPill(o)} />
            ))}
          </RecordList>
        )}
        {section === 'challenges' && (
          <RecordList empty={t('acme.noActiveChallenges')}>
            {challenges.map((ch, i) => (
              <RecordRow key={ch.id ?? i} title={`${ch.type} · ${ch.domain}`} meta={challengeWhere(t, ch)} badge={orderPill(ch)} />
            ))}
          </RecordList>
        )}
      </DockBody>
      {confirming && (
        <AtelierDialog size="narrow" title={t('acme.disableTitle')} onClose={() => setConfirming(false)} returnTo="acme-disable">
          <div className="notice warn"><Icon name="warning" /><span>{t('acme.disableWarning', { name })}</span></div>
          <Props items={[[t('acme.tabs.account'), <span key="n" className="mono">{name}</span>], [t('acme.contact'), currentEmail || '—'], [t('acme.accountKey'), account.key_type || '—']]} />
          <div className="modal-actions">
            <Btn onClick={() => setConfirming(false)}>{t('common.cancel')}</Btn>
            <Btn tone="danger" icon="block" id="acme-disable-confirm" onClick={async () => { setConfirming(false); await onDeactivate(account.id) }}>
              {t('acme.disableConfirm')}
            </Btn>
          </div>
        </AtelierDialog>
      )}
      {editing && (
        <AtelierDialog size="narrow" title={t('acme.editEmail')} onClose={() => setEditing(false)} returnTo="acme-edit-email">
          <div className="form-fields">
            <div className="field full">
              <label htmlFor="acme-email">{t('common.email')}</label>
              <input id="acme-email" data-autofocus type="email" value={emailDraft} placeholder="admin@example.com" aria-describedby="acme-email-hint"
                onChange={(e) => setEmailDraft(e.target.value)} />
              <small id="acme-email-hint">{t('acme.editEmailCaveat')}</small>
            </div>
          </div>
          <div className="modal-actions">
            <Btn onClick={() => setEditing(false)}>{t('common.cancel')}</Btn>
            <Btn tone="primary" icon="check" onClick={saveEmail}>{t('common.save')}</Btn>
          </div>
        </AtelierDialog>
      )}
    </Dock>
  )
}
