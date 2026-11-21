/**
 * Pin templates to a CA in the mockup's modal(): the count, then each template as a record row
 * (name, description, Épinglé or Inactif, Épingler / Désépingler), then Fermer.
 */
import { useState, useEffect } from 'react'
import { AtelierDialog, Pill, RecordList, RecordRow } from '../atelier'
import { templatesService } from '../../services'
import { useNotification } from '../../contexts'

export function ManageTemplatePinsModal({ open, onOpenChange, ca, t }) {
  if (!open) return null
  return <PinsBody onOpenChange={onOpenChange} ca={ca} t={t} />
}

function PinsBody({ onOpenChange, ca, t }) {
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState({})
  const { showSuccess, showError } = useNotification()

  const loadTemplates = async () => {
    setLoading(true)
    try {
      const res = await templatesService.getAllForCA(ca.id)
      const list = res?.data || res || []
      setTemplates(Array.isArray(list) ? list : [])
    } catch (err) {
      showError(err.message || t('common.error'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (ca?.id) loadTemplates()
  }, [ca?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleTogglePin = async (template) => {
    setSaving(prev => ({ ...prev, [template.id]: true }))
    try {
      if (template.is_pinned) {
        await templatesService.unpinFromCA(ca.id, template.id)
        showSuccess(t('templates.unpinSuccess'))
      } else {
        await templatesService.pinToCA(ca.id, template.id)
        showSuccess(t('templates.pinSuccess'))
      }
      await loadTemplates()
    } catch (err) {
      showError(err.message || t('common.error'))
    } finally {
      setSaving(prev => ({ ...prev, [template.id]: false }))
    }
  }

  const pinnedCount = templates.filter(tpl => tpl.is_pinned).length
  const close = () => onOpenChange(false)

  return (
    <AtelierDialog title={t('templates.managePins')} subtitle={ca?.descr || ca?.common_name} onClose={close} testId="template-pins-dialog">
      {loading ? (
        <p className="small muted" role="status">{t('common.loading')}</p>
      ) : (
        <>
          <p className="small muted" style={{ marginBottom: 8 }}>
            {pinnedCount > 0 ? t('templates.pinnedCount', { count: pinnedCount, total: templates.length }) : t('templates.noPinnedTemplates')}
          </p>
          <RecordList>
            {templates.map(template => (
              <RecordRow key={template.id} title={template.name} meta={template.description || undefined}
                // A deactivated template stays marked Inactif, pinned or not
                badge={(template.is_pinned || template.is_active === false) && (
                  <span className="ca-badges">
                    {template.is_pinned && <Pill tone="good" icon="pin" label={t('templates.pinned')} />}
                    {template.is_active === false && <span title={t('templates.deactivateTooltip')}><Pill tone="muted" label={t('common.inactive')} /></span>}
                  </span>
                )}
                // A deactivated template can be unpinned, not pinned: the server refuses it
                action={(template.is_pinned || template.is_active !== false) && (
                  <button type="button" className={template.is_pinned ? 'btn danger' : 'btn'} data-write="" disabled={saving[template.id] || undefined}
                    onClick={() => handleTogglePin(template)}>
                    {saving[template.id] ? t('common.loading') : template.is_pinned ? t('templates.unpinFromCA') : t('templates.pinToCA')}
                  </button>
                )} />
            ))}
          </RecordList>
        </>
      )}
      <div className="modal-actions">
        <button type="button" className="btn primary" data-action="close-modal" data-write="false" onClick={close}>{t('common.close')}</button>
      </div>
    </AtelierDialog>
  )
}
