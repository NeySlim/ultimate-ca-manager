/**
 * Policies: the mockup's policies module, a simplePage() list (Portée, État) with its one-object
 * dock (Aperçu), on the server's certificate policies. What the product has more (operations,
 * priority, approval, the rules, search and operation filter, creation, edit, enable / disable and
 * removal) takes the mockup's toolbar, further columns, dock actions and sections, and its form
 * dialog. The mockup's Exceptions column and « En observation » state have no data (G03, G04).
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Zone, Icon, Btn, Pill, PageHead, Toolbar, SearchField, FilterSelect, ListView, Dock, DockBody,
  Section, Props, LoadError, LoadCause, EmptyBlock, NoMatch, AtelierDialog, useClientList, useSortParam,
} from '../components/atelier'
import { policiesService, casService, groupsService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, usePersistedState } from '../hooks'
import { useDockSelection } from '../components/atelier/useDockParam'
import { formatDate } from '../lib/utils'
import { useKeyPlatform } from '../lib/policyAlgorithms'
import { KEY_ALGORITHMS, KEY_GROUPS, isBrainpool, isUsable } from '../lib/keyAlgorithms'

// Operations a policy governs
const POLICY_TYPES = [
  { value: 'issuance', labelKey: 'policies.policyType.issuance', helpKey: 'policies.operationHelp.issuance' },
  { value: 'renewal', labelKey: 'policies.policyType.renewal', helpKey: 'policies.operationHelp.renewal' },
  { value: 'revocation', labelKey: 'policies.policyType.revocation', helpKey: 'policies.operationHelp.revocation' },
]

// Signature hashes; none selected means any hash
const DIGEST_OPTIONS = [
  { value: 'sha256', label: 'SHA-256' },
  { value: 'sha384', label: 'SHA-384' },
  { value: 'sha512', label: 'SHA-512' },
]

const DEFAULT_FORM = {
  name: '',
  description: '',
  operations: ['issuance'],
  ca_id: null,
  template_id: null,
  requires_approval: false,
  approval_group_id: null,
  min_approvers: 1,
  notify_on_violation: true,
  is_active: true,
  priority: 100,
  rules: {
    max_validity_days: 397,
    allowed_key_types: [],
    allowed_digests: [],
    san_restrictions: {
      max_dns_names: 50,
      dns_pattern: '',
    },
  },
  notification_emails: [],
}

// Same shape the server accepts: one mailbox, no separators or brackets
const EMAIL_RE = /^[^@\s,;<>"]+@[^@\s,;<>"]+$/

function parseEmails(text) {
  const emails = (text || '').split(/[\s,;]+/).filter(Boolean)
  return { emails, invalid: emails.filter(e => !EMAIL_RE.test(e)) }
}

// Policies read in the order the server evaluates them (T4), kept in the address
const BY_PRIORITY = { key: 'priority', asc: true }
const SORT_KEYS = ['name', 'scope', 'operations', 'priority', 'approval', 'state']
const STATES = { applied: 'good', inactive: 'muted' }
const stateOf = (p) => (p.is_active ? 'applied' : 'inactive')

/** The create and edit form, in the mockup's dialog and fields. */
function PolicyDialog({ editing, cas, groups, keyTypeOptions, saving, onSave, onClose }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState(() => (editing ? {
    name: editing.name || '',
    description: editing.description || '',
    operations: Array.isArray(editing.operations) ? editing.operations : ['issuance'],
    ca_id: editing.ca_id || null,
    template_id: editing.template_id || null,
    requires_approval: editing.requires_approval || false,
    approval_group_id: editing.approval_group_id || null,
    min_approvers: editing.min_approvers || 1,
    notify_on_violation: editing.notify_on_violation ?? true,
    is_active: editing.is_active ?? true,
    priority: editing.priority || 100,
    // The update replaces the rules: keys the form does not show go back unchanged
    rules: {
      ...(editing.rules || {}),
      max_validity_days: editing.rules?.max_validity_days || 397,
      allowed_key_types: editing.rules?.allowed_key_types || [],
      allowed_digests: editing.rules?.allowed_digests || [],
      san_restrictions: {
        ...(editing.rules?.san_restrictions || {}),
        max_dns_names: editing.rules?.san_restrictions?.max_dns_names || 50,
        dns_pattern: editing.rules?.san_restrictions?.dns_pattern || '',
      },
    },
    notification_emails: editing.notification_emails || [],
  } : { ...DEFAULT_FORM, rules: { ...DEFAULT_FORM.rules, san_restrictions: { ...DEFAULT_FORM.rules.san_restrictions } } }))
  const [emailsText, setEmailsText] = useState(() => (editing?.notification_emails || []).join('\n'))
  const parsedEmails = parseEmails(emailsText)
  // A key this server cannot use (FIPS mode, no ML-DSA) shows only while ticked, so it can be removed
  const shownKeyTypes = keyTypeOptions.filter(opt => opt.usable || formData.rules.allowed_key_types?.includes(opt.value))
  const noOperation = !(formData.operations || []).length

  const set = (field, value) => setFormData(p => ({ ...p, [field]: value }))
  const updateRule = (key, value) => setFormData(p => ({ ...p, rules: { ...p.rules, [key]: value } }))
  const updateSan = (key, value) => setFormData(p => ({ ...p, rules: { ...p.rules, san_restrictions: { ...p.rules.san_restrictions, [key]: value } } }))
  const toggle = (list, value) => (list.includes(value) ? list.filter(v => v !== value) : [...list, value])

  const submit = (e) => {
    e.preventDefault()
    if (!formData.name.trim() || noOperation || parsedEmails.invalid.length) return
    onSave({ ...formData, notification_emails: parsedEmails.emails })
  }
  const check = (name, checked, onChange, label, help) => (
    <label className="checkbox-line" key={name}>
      <input type="checkbox" name={name} checked={checked} onChange={onChange} />
      <span>{label}{help && <small>{help}</small>}</span>
    </label>
  )

  return (
    <AtelierDialog title={editing ? t('policies.editPolicy') : t('policies.createPolicy')} subtitle={editing?.name} onClose={onClose} testId="policy-dialog">
      <form id="policy-form" noValidate onSubmit={submit}>
        <div className="form-fields">
          <div className="field full">
            <label htmlFor="pol-name">{t('policies.policyName')}</label>
            <input id="pol-name" value={formData.name} required data-autofocus="" placeholder={t('policies.policyNamePlaceholder')}
              onChange={(e) => set('name', e.target.value)} />
          </div>
          <fieldset className="field full">
            <legend>{t('policies.operations')}</legend>
            <div className="eku-list">
              {POLICY_TYPES.map(op => check(`op-${op.value}`, (formData.operations || []).includes(op.value),
                () => set('operations', toggle(formData.operations || [], op.value)), t(op.labelKey), t(op.helpKey)))}
            </div>
            {noOperation && <p className="field-error" id="err-pol-ops"><Icon name="warning" /><span>{t('policies.operationsRequired')}</span></p>}
          </fieldset>
          <div className="field full">
            <label htmlFor="pol-desc">{t('common.description')}</label>
            <textarea id="pol-desc" rows={2} value={formData.description} placeholder={t('policies.descriptionPlaceholder')}
              onChange={(e) => set('description', e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="pol-ca">{t('policies.targetCA')}</label>
            <select id="pol-ca" value={formData.ca_id?.toString() || ''} onChange={(e) => set('ca_id', e.target.value ? parseInt(e.target.value, 10) : null)}>
              <option value="">{t('policies.allCAs')}</option>
              {cas.map(ca => <option key={ca.id} value={ca.id.toString()}>{ca.common_name}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="pol-priority">{t('policies.priority')}</label>
            <input id="pol-priority" type="number" min={1} max={1000} value={formData.priority}
              onChange={(e) => set('priority', parseInt(e.target.value, 10) || 100)} />
          </div>
          <p className="field full small muted">
            <strong>{t('policies.rules')}</strong> · {t('policies.rulesEnforcedHelp')}
            {!(formData.operations || []).some(op => op === 'issuance' || op === 'renewal') && <> {t('policies.rulesRevocationOnly')}</>}
          </p>
          <div className="field">
            <label htmlFor="pol-validity">{t('policies.maxValidity')}</label>
            <input id="pol-validity" type="number" min={1} max={3650} value={formData.rules.max_validity_days}
              onChange={(e) => updateRule('max_validity_days', parseInt(e.target.value, 10) || 397)} />
          </div>
          <div className="field">
            <label htmlFor="pol-sans">{t('policies.maxSANs')}</label>
            <input id="pol-sans" type="number" min={1} max={500} value={formData.rules.san_restrictions?.max_dns_names || 50}
              onChange={(e) => updateSan('max_dns_names', parseInt(e.target.value, 10) || 50)} />
          </div>
          <fieldset className="field full">
            <legend>{t('policies.allowedKeyTypes')}</legend>
            {[...new Set(shownKeyTypes.map(o => o.group))].map(group => (
              <div key={group} className="eku-list" role="group" aria-label={group}>
                <small>{group}</small>
                {shownKeyTypes.filter(opt => opt.group === group).map(opt => check(`key-${opt.value}`, !!formData.rules.allowed_key_types?.includes(opt.value),
                  () => updateRule('allowed_key_types', toggle(formData.rules.allowed_key_types || [], opt.value)), opt.label))}
              </div>
            ))}
            {(formData.rules.allowed_key_types || []).some(isBrainpool) && (
              <p className="notice warn" role="note" style={{ margin: 0 }}><Icon name="warning" />{t('common.keyGroups.brainpoolWarning')}</p>
            )}
            <small>{t('policies.allowedKeyTypesHelp')}</small>
          </fieldset>
          <fieldset className="field full">
            <legend>{t('policies.allowedDigests')}</legend>
            <div className="eku-list">
              {DIGEST_OPTIONS.map(opt => check(`digest-${opt.value}`, !!formData.rules.allowed_digests?.includes(opt.value),
                () => updateRule('allowed_digests', toggle(formData.rules.allowed_digests || [], opt.value)), opt.label))}
            </div>
            <small>{t('policies.allowedDigestsHelp')}</small>
          </fieldset>
          <div className="field full">
            <label htmlFor="pol-dns">{t('policies.dnsPattern')}</label>
            <input id="pol-dns" value={formData.rules.san_restrictions?.dns_pattern || ''} placeholder="*.company.com" spellCheck={false}
              onChange={(e) => updateSan('dns_pattern', e.target.value)} />
          </div>
          <div className="field full">
            {check('requires-approval', formData.requires_approval, (e) => set('requires_approval', e.target.checked), t('policies.requireApproval'))}
          </div>
          {formData.requires_approval && (
            <>
              <div className="field">
                <label htmlFor="pol-group">{t('policies.approvalGroup')}</label>
                <select id="pol-group" value={formData.approval_group_id?.toString() || ''}
                  onChange={(e) => set('approval_group_id', e.target.value ? parseInt(e.target.value, 10) : null)}>
                  <option value="">{t('policies.selectGroup')}</option>
                  {groups.map(g => <option key={g.id} value={g.id.toString()}>{g.name}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="pol-approvers">{t('policies.minApprovers')}</label>
                <input id="pol-approvers" type="number" min={1} max={10} value={formData.min_approvers}
                  onChange={(e) => set('min_approvers', parseInt(e.target.value, 10) || 1)} />
              </div>
            </>
          )}
          <div className="field full">
            {check('notify', formData.notify_on_violation, (e) => set('notify_on_violation', e.target.checked), t('policies.notifyOnViolation'), t('policies.notifyHelp'))}
          </div>
          {formData.notify_on_violation && (
            <div className="field full">
              <label htmlFor="pol-emails">{t('policies.notificationEmails')}</label>
              <textarea id="pol-emails" rows={2} value={emailsText} placeholder="pki-team@example.com" spellCheck={false}
                aria-invalid={parsedEmails.invalid.length > 0 || undefined}
                aria-describedby={parsedEmails.invalid.length ? 'hint-pol-emails err-pol-emails' : 'hint-pol-emails'}
                onChange={(e) => setEmailsText(e.target.value)} />
              {parsedEmails.invalid.length > 0 && (
                <p className="field-error" id="err-pol-emails"><Icon name="warning" /><span>{t('policies.invalidEmails', { emails: parsedEmails.invalid.join(', ') })}</span></p>
              )}
              <small id="hint-pol-emails">{t('policies.notificationEmailsHelp')}</small>
            </div>
          )}
        </div>
        <div className="modal-actions">
          <Btn data-action="close-modal" onClick={onClose}>{t('common.cancel')}</Btn>
          <Btn type="submit" tone="primary" icon={editing ? 'check' : 'plus'}
            disabled={saving || !formData.name.trim() || noOperation || parsedEmails.invalid.length > 0 || undefined}>
            {editing ? t('common.update') : t('common.create')}
          </Btn>
        </div>
      </form>
    </AtelierDialog>
  )
}

const POLICY_SECTIONS = ['overview']

export default function PoliciesPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { canWrite, canDelete, hasPermission } = usePermission()

  // FIPS mode puts a read-only system policy ahead of these, without EdDSA keys
  const platform = useKeyPlatform()
  const keyTypeOptions = useMemo(
    () => KEY_ALGORITHMS.map(a => ({
      value: a.label,
      label: a.i18nKey ? t(a.i18nKey) : a.display,
      group: t(KEY_GROUPS.find(g => g.id === a.group).labelKey),
      usable: isUsable(a, platform),
    })),
    [t, platform],
  )

  const [policies, setPolicies] = useState([])
  const [cas, setCas] = useState([])
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [dialog, setDialog] = useState(null) // { kind: 'form', editing } | { kind: 'delete', policy }
  // The open policy and its section live in the URL (`item`, `section`)
  const policyDock = useDockSelection(policies, { ready: !loading && !loadError, sections: POLICY_SECTIONS })
  const openId = policyDock.selected?.id ?? null
  const { section, setSection } = policyDock
  const [saving, setSaving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')
  const [type, setType] = usePersistedState('ucm-policies-operation', '')
  const [state, setState] = usePersistedState('ucm-policies-state', '')

  const loadData = useCallback(async () => {
    setLoadError(null)
    try {
      const [policiesRes, casRes, groupsRes] = await Promise.all([
        policiesService.list(),
        casService.getAll().catch(() => ({ data: [] })),
        groupsService.getAll().catch(() => ({ data: [] })),
      ])
      setCas(casRes?.data || [])
      setGroups(groupsRes?.data || [])
      setPolicies(Array.isArray(policiesRes?.data) ? policiesRes.data : [])
    } catch (err) {
      setLoadError(err || {})
      showError(t('policies.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [showError, t])
  useEffect(() => { loadData() }, [loadData])

  const save = async (payload) => {
    const editing = dialog?.editing
    try {
      setSaving(true)
      if (editing) {
        await policiesService.update(editing.id, payload)
        showSuccess(t('policies.updated'))
      } else {
        await policiesService.create(payload)
        showSuccess(t('policies.created'))
      }
      setDialog(null)
      loadData()
    } catch {
      showError(t('policies.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const toggleActive = async (policy) => {
    if (busy) return
    try {
      setBusy(true)
      await policiesService.toggle(policy.id)
      showSuccess(policy.is_active ? t('policies.disabled') : t('policies.enabled'))
      loadData()
    } catch {
      showError(t('policies.toggleFailed'))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (policy) => {
    if (busy) return
    try {
      setBusy(true)
      await policiesService.delete(policy.id)
      showSuccess(t('policies.deleted'))
      setDialog(null)
      policyDock.select(null)
      loadData()
    } catch {
      showError(t('policies.deleteFailed'))
    } finally {
      setBusy(false)
    }
  }

  // The list reads by priority, the order the server applies them in, then by name
  const sorted = useMemo(() => [...policies].sort((a, b) => (a.priority ?? 100) - (b.priority ?? 100) || String(a.name).localeCompare(String(b.name))), [policies])
  const operationsOf = (p) => (p.operations?.length
    ? POLICY_TYPES.filter(o => p.operations.includes(o.value)).map(o => t(o.labelKey)).join(', ')
    : t('policies.noOperation'))
  const scopeOf = (p) => p.ca_name || t('policies.allCAs')
  const approvalOf = (p) => (p.requires_approval ? [`${p.min_approvers || 1}+`, p.approval_group_name].filter(Boolean).join(' ') : t('common.no'))
  const searched = useMemo(() => {
    const q = query.trim().toLowerCase()
    return sorted.filter(p => (!type || (p.operations || []).includes(type))
      && (!q || [p.name, p.description, p.policy_type, p.ca_name].some(v => String(v || '').toLowerCase().includes(q))))
  }, [sorted, type, query])
  const present = Object.keys(STATES).filter(s => policies.some(p => stateOf(p) === s))
  const active = present.includes(state) ? state : ''
  const rows = searched.filter(p => !active || stateOf(p) === active)
  const sortParam = useSortParam(BY_PRIORITY, SORT_KEYS)
  const list = useClientList(rows, {
    sortParam,
    resetKey: `${query}|${type}|${active}`,
    sorts: {
      name: (p) => p.name, scope: scopeOf, operations: operationsOf, priority: (p) => p.priority ?? 100,
      approval: (p) => (p.requires_approval ? p.min_approvers || 1 : 0), state: (p) => Object.keys(STATES).indexOf(stateOf(p)),
    },
  })
  const views = [
    { id: '', label: t('common.all'), count: searched.length },
    ...present.map(s => ({ id: s, label: t(`policies.state.${s}`), count: searched.filter(p => stateOf(p) === s).length })),
  ]
  const narrowed = Boolean(query.trim() || type || active)
  const pill = (p) => <Pill label={t(`policies.state.${stateOf(p)}`)} tone={STATES[stateOf(p)]} />
  const open = policies.find(p => p.id === openId) || null
  const create = canWrite('policies') ? { label: t('policies.createPolicy'), icon: 'plus', primary: true, onClick: () => setDialog({ kind: 'form', editing: null }) } : undefined
  const r = open?.rules || {}

  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('common.policies') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: open.name, icon: 'policy' }]} onClose={() => policyDock.select(null)}>
      <DockBody icon="policy" title={open.name} badge={pill(open)} section={section} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: open.name })} sections={[['overview', t('atelier.overview')]]}
        actions={<>
          {canWrite('policies') && <Btn icon="settings" id="policy-edit" write onClick={() => setDialog({ kind: 'form', editing: open })}>{t('common.edit')}</Btn>}
          {canWrite('policies') && (
            <Btn icon={open.is_active ? 'block' : 'check'} id="policy-toggle" write disabled={busy || undefined} onClick={() => toggleActive(open)}>
              {open.is_active ? t('policies.disable') : t('policies.enable')}
            </Btn>
          )}
          {canDelete('policies') && <Btn tone="danger" icon="block" id="policy-delete" onClick={() => setDialog({ kind: 'delete', policy: open })}>{t('policies.deletePolicy')}…</Btn>}
        </>}>
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Props items={[
              [t('policies.scope'), scopeOf(open)],
              [t('atelier.state'), pill(open)],
              [t('policies.operations'), operationsOf(open)],
              [t('policies.priority'), <span className="mono">{open.priority}</span>],
              [t('policies.approval'), approvalOf(open)],
              [t('common.createdAt'), formatDate(open.created_at)],
              open.created_by && [t('common.createdBy'), open.created_by],
            ]} />
          </Section>
          <Section title={t('atelier.summary')}>
            <p className="summary">{open.description || <span className="muted">{t('policies.noDescription')}</span>}</p>
          </Section>
          <Section title={t('policies.rules')}>
            <Props items={[
              r.max_validity_days > 0 && [t('policies.maxValidity'), r.max_validity_days],
              r.san_restrictions?.max_dns_names > 0 && [t('policies.maxSANs'), r.san_restrictions.max_dns_names],
              [t('policies.allowedKeyTypes'), r.allowed_key_types?.length ? r.allowed_key_types.join(', ') : <span className="muted">{t('policies.anyKeyType')}</span>],
              [t('policies.allowedDigests'), r.allowed_digests?.length
                ? r.allowed_digests.map(d => DIGEST_OPTIONS.find(o => o.value === d)?.label || d).join(', ')
                : <span className="muted">{t('policies.anyDigest')}</span>],
              r.san_restrictions?.dns_pattern && [t('policies.dnsPattern'), <span className="mono">{r.san_restrictions.dns_pattern}</span>],
            ]} />
          </Section>
          {open.requires_approval && (
            <Section title={t('policies.approvalWorkflow')}>
              <Props items={[
                [t('policies.approvalGroup'), open.approval_group_name || '—'],
                [t('policies.minApprovers'), open.min_approvers],
              ]} />
            </Section>
          )}
        </div>
      </DockBody>
    </Dock>
  )

  return (
    <Zone dock={dock} after={<>
      {dialog?.kind === 'form' && (
        <PolicyDialog editing={dialog.editing} cas={cas} groups={groups} keyTypeOptions={keyTypeOptions} saving={saving}
          onSave={save} onClose={() => setDialog(null)} />
      )}
      {dialog?.kind === 'delete' && (
        <AtelierDialog title={t('policies.deletePolicy')} subtitle={dialog.policy.name} size="narrow" onClose={() => setDialog(null)} testId="policy-delete-dialog">
          <div className="notice warn"><Icon name="warning" />{t('policies.deleteConfirm', { name: dialog.policy.name })}</div>
          <div className="modal-actions">
            <Btn data-action="close-modal" onClick={() => setDialog(null)}>{t('common.cancel')}</Btn>
            <Btn tone="danger" icon="block" disabled={busy || undefined} onClick={() => remove(dialog.policy)}>{t('common.delete')}</Btn>
          </div>
        </AtelierDialog>
      )}
    </>}>
      <PageHead title={t('common.policies')} total={t('policies.unit', { count: policies.length })} intent={t('shell.moduleDesc.policies')}
        actions={create && <Btn tone="primary" icon="plus" id="policy-new" onClick={create.onClick}>{create.label}</Btn>} />
      {platform.fips && (
        <div className="notice" role="note"><Icon name="shield" /><span><strong>{t('policies.fipsRulesTitle')}</strong> {t('policies.fipsRulesDesc')}</span></div>
      )}
      <ListView label={t('common.policies')} caption={t('policies.caption')} icon="policy" list={list} nameSort="name" loading={loading}
        filters={{ views, active, onChange: setState, label: t('policies.filterByState') }}
        toolbar={(
          <Toolbar>
            <SearchField id="policy-search" name="q" label={t('policies.searchPlaceholder')} placeholder={t('policies.searchPlaceholder')} value={query} onChange={setQuery} />
            <FilterSelect id="policy-operation" label={t('policies.operations')} value={type} onChange={setType}
              options={[{ value: '', label: t('policies.allTypes') }, ...POLICY_TYPES.map(o => ({ value: o.value, label: t(o.labelKey) }))]} />
          </Toolbar>
        )}
        title={(p) => p.name} status={pill} openedId={openId}
        onOpen={(p) => policyDock.select(p)}
        columns={[
          { id: 'scope', label: t('policies.scope'), cell: scopeOf, kind: 'text', priority: 3, sort: 'scope' },
          { id: 'operations', label: t('policies.operations'), cell: operationsOf, kind: 'text', priority: 4, sort: 'operations' },
          { id: 'priority', label: t('policies.priority'), cell: (p) => p.priority, kind: 'number', priority: 2, sort: 'priority' },
          { id: 'approval', label: t('policies.approval'), cell: approvalOf, kind: 'text', priority: 3, sort: 'approval' },
          { status: true, sort: 'state' },
        ]}
        error={loadError && (
          <LoadError id="policies" title={t('policies.loadFailed')} onRetry={() => { setLoading(true); loadData() }} journal={hasPermission('read:audit') && '/audit'}
            cause={<LoadCause error={{ status: loadError.status, request: loadError.status && 'GET /api/v2/policies', message: loadError.message }} />} />
        )}
        empty={narrowed && policies.length ? (
          <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')}
            onReset={() => { setQuery(''); setType(''); setState('') }} />
        ) : (
          <EmptyBlock id="policies" icon="policy" title={t('policies.noPolicies')} text={t('policies.noPoliciesDesc')} action={create} />
        )}
        footer={{ range: t('policies.range', list.counts(policies.length)) }} />
    </Zone>
  )
}
