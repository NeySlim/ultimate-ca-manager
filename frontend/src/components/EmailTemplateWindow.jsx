/**
 * EmailTemplateWindow — Floating window with split-pane email template editor
 * 
 * Features:
 * - Split pane: HTML source editor (left) + live preview (right)
 * - Debounced live preview that auto-refreshes as you type
 * - Reset to default template
 * - Save action
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { FloatingWindow } from './ui/FloatingWindow'
import { Button } from './Button'
import {
  EnvelopeSimple, ArrowCounterClockwise, FloppyDisk,
  ArrowsClockwise, Info
} from '@phosphor-icons/react'
import { apiClient } from '../services/apiClient'
import { useNotification } from '../contexts/NotificationContext'

const TEMPLATE_VARS = [
  { var: '{{logo}}', desc: 'templateVarLogo' },
  { var: '{{title}}', desc: 'templateVarTitle' },
  { var: '{{title_color}}', desc: 'templateVarTitleColor' },
  { var: '{{content}}', desc: 'templateVarContent' },
  { var: '{{datetime}}', desc: 'templateVarDatetime' },
  { var: '{{instance_url}}', desc: 'templateVarInstanceUrl' },
]

export default function EmailTemplateWindow({ onClose }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  
  const [template, setTemplate] = useState('')
  const [defaultTemplate, setDefaultTemplate] = useState('')
  const [isCustom, setIsCustom] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [previewHtml, setPreviewHtml] = useState('')
  const [dirty, setDirty] = useState(false)
  const previewTimer = useRef(null)

  // Load template + initial preview
  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiClient.get('/settings/email/template')
        setTemplate(res.data.template)
        setDefaultTemplate(res.data.default_template)
        setIsCustom(res.data.is_custom)
        // Load initial preview
        const prev = await apiClient.post('/settings/email/template/preview', { template: res.data.template })
        setPreviewHtml(prev.data.html)
      } catch (err) {
        showError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
    return () => { if (previewTimer.current) clearTimeout(previewTimer.current) }
  }, [])

  // Debounced preview refresh
  const refreshPreview = useCallback((html) => {
    if (previewTimer.current) clearTimeout(previewTimer.current)
    previewTimer.current = setTimeout(async () => {
      try {
        const res = await apiClient.post('/settings/email/template/preview', { template: html })
        setPreviewHtml(res.data.html)
      } catch {
        // Silently fail on preview errors during typing
      }
    }, 800)
  }, [])

  const handleSourceChange = useCallback((e) => {
    const val = e.target.value
    setTemplate(val)
    setDirty(true)
    refreshPreview(val)
  }, [refreshPreview])

  const handleSave = async () => {
    setSaving(true)
    try {
      await apiClient.patch('/settings/email/template', { template })
      setIsCustom(true)
      setDirty(false)
      showSuccess(t('settings.templateSaved'))
    } catch (err) {
      showError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    if (!window.confirm(t('settings.templateResetConfirm'))) return
    try {
      await apiClient.post('/settings/email/template/reset')
      setTemplate(defaultTemplate)
      setIsCustom(false)
      setDirty(false)
      refreshPreview(defaultTemplate)
      showSuccess(t('settings.templateResetSuccess'))
    } catch (err) {
      showError(err.message)
    }
  }

  return (
    <FloatingWindow
      storageKey="email-template-editor"
      defaultPos={{ x: 80, y: 40, w: 1100, h: 700 }}
      constraints={{ minW: 700, minH: 400 }}
      onClose={onClose}
      title={t('settings.emailTemplate')}
      subtitle={isCustom ? t('settings.templateCustom') : t('settings.templateDefault')}
      icon={EnvelopeSimple}
      iconClass="icon-bg-blue"
      zIndex={60}
    >
      <div className="flex flex-col h-full overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border bg-bg-primary">
          <div className="flex items-start gap-2 min-w-0">
            <Info size={14} className="shrink-0 mt-0.5 text-accent-primary" />
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-text-secondary">
              {TEMPLATE_VARS.map(v => (
                <span key={v.var}>
                  <code className="text-accent-primary font-mono text-[11px]">{v.var}</code>
                  <span className="ml-1">{t(`settings.${v.desc}`)}</span>
                </span>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {isCustom && (
              <Button variant="ghost" size="xs" onClick={handleReset}>
                <ArrowCounterClockwise size={14} />
                {t('settings.templateResetDefault')}
              </Button>
            )}
            <Button variant="primary" size="xs" onClick={handleSave} disabled={saving || !dirty}>
              {saving ? <ArrowsClockwise size={14} className="animate-spin" /> : <FloppyDisk size={14} />}
              {t('common.save')}
            </Button>
          </div>
        </div>

        {/* Split pane: HTML source + Preview */}
        <div className="flex-1 flex min-h-0">
          {loading ? (
            <div className="flex items-center justify-center w-full text-text-tertiary">
              <ArrowsClockwise size={20} className="animate-spin" />
            </div>
          ) : (
            <>
              {/* HTML Source Editor */}
              <div className="w-1/2 flex flex-col border-r border-border min-h-0">
                <div className="px-3 py-1.5 bg-bg-tertiary/50 border-b border-border text-[11px] font-medium text-text-tertiary uppercase tracking-wider">
                  HTML Source
                </div>
                <textarea
                  value={template}
                  onChange={handleSourceChange}
                  className="flex-1 w-full p-3 bg-bg-primary text-text-primary font-mono text-[12px] leading-[1.6] resize-none focus:outline-none"
                  spellCheck={false}
                />
              </div>

              {/* Live Preview */}
              <div className="w-1/2 flex flex-col min-h-0">
                <div className="px-3 py-1.5 bg-bg-tertiary/50 border-b border-border text-[11px] font-medium text-text-tertiary uppercase tracking-wider">
                  {t('settings.templatePreview')}
                </div>
                <div className="flex-1 overflow-auto bg-[#f4f5f7]">
                  <iframe
                    srcDoc={previewHtml}
                    title="Email Preview"
                    className="w-full h-full border-0"
                    sandbox="allow-same-origin"
                    style={{ minHeight: '100%' }}
                  />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </FloatingWindow>
  )
}
