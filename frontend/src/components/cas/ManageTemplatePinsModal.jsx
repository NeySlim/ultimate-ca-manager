/**
 * Manage Template Pins Modal
 * Allows pinning/unpinning templates to a specific CA
 */
import { useState, useEffect } from 'react'
import { PushPin, PushPinSlash, Check, X } from '@phosphor-icons/react'
import { Button, Modal, LoadingSpinner } from '../index'
import { templatesService } from '../../services'
import { useNotification } from '../../contexts'

export function ManageTemplatePinsModal({ open, onOpenChange, ca, t }) {
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState({})
  const { showSuccess, showError } = useNotification()

  useEffect(() => {
    if (open && ca?.id) {
      loadTemplates()
    }
  }, [open, ca?.id])

  const loadTemplates = async () => {
    setLoading(true)
    try {
      const res = await templatesService.getForCA(ca.id)
      const list = res?.data || res || []
      setTemplates(Array.isArray(list) ? list : [])
    } catch (err) {
      showError(err.message || t('common.error'))
    } finally {
      setLoading(false)
    }
  }

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
      // Reload to update status
      await loadTemplates()
    } catch (err) {
      showError(err.message || t('common.error'))
    } finally {
      setSaving(prev => ({ ...prev, [template.id]: false }))
    }
  }

  const pinnedCount = templates.filter(t => t.is_pinned).length

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={t('templates.managePins')}
      description={ca?.descr || ca?.common_name}
      size="md"
    >
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <LoadingSpinner />
        </div>
      ) : (
        <div className="space-y-4">
          {/* Summary */}
          <div className="text-sm text-text-secondary">
            {pinnedCount > 0 
              ? t('templates.pinnedCount', { count: pinnedCount, total: templates.length })
              : t('templates.noPinnedTemplates')
            }
          </div>

          {/* Template list */}
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {templates.map(template => (
              <div
                key={template.id}
                className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-bg-secondary transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-text-primary truncate">
                      {template.name}
                    </span>
                    {template.is_pinned && (
                      <PushPin size={16} className="text-accent-primary shrink-0" weight="fill" />
                    )}
                  </div>
                  {template.description && (
                    <p className="text-xs text-text-tertiary mt-0.5 truncate">
                      {template.description}
                    </p>
                  )}
                </div>

                <Button
                  type="button"
                  size="xs"
                  variant={template.is_pinned ? 'danger' : 'primary'}
                  onClick={() => handleTogglePin(template)}
                  disabled={saving[template.id]}
                  className="shrink-0 ml-3"
                >
                  {saving[template.id] ? (
                    <LoadingSpinner size="xs" />
                  ) : template.is_pinned ? (
                    <>
                      <PushPinSlash size={14} />
                      <span className="ml-1">{t('templates.unpinFromCA')}</span>
                    </>
                  ) : (
                    <>
                      <PushPin size={14} />
                      <span className="ml-1">{t('templates.pinToCA')}</span>
                    </>
                  )}
                </Button>
              </div>
            ))}
          </div>

          {/* Close button */}
          <div className="flex justify-end pt-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
            >
              {t('common.close')}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
