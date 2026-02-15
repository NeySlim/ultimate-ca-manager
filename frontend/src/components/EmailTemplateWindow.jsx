/**
 * EmailTemplateWindow — Floating window with WYSIWYG email template editor
 * 
 * Features:
 * - TipTap WYSIWYG editor for HTML template editing
 * - Raw HTML source view toggle
 * - Live preview with rendered template
 * - Reset to default template
 * - Save/cancel actions
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { FloatingWindow } from './ui/FloatingWindow'
import { Button } from './Button'
import EmailTemplateEditor from './EmailTemplateEditor'
import {
  EnvelopeSimple, Eye, Code, ArrowCounterClockwise, FloppyDisk,
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
  const [mode, setMode] = useState('visual') // visual, source, preview
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewing, setPreviewing] = useState(false)
  const [dirty, setDirty] = useState(false)

  // Load template
  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiClient.get('/settings/email/template')
        setTemplate(res.data.template)
        setDefaultTemplate(res.data.default_template)
        setIsCustom(res.data.is_custom)
      } catch (err) {
        showError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const handleChange = useCallback((html) => {
    setTemplate(html)
    setDirty(true)
  }, [])

  const handleSourceChange = useCallback((e) => {
    setTemplate(e.target.value)
    setDirty(true)
  }, [])

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
      showSuccess(t('settings.templateResetSuccess'))
    } catch (err) {
      showError(err.message)
    }
  }

  const handlePreview = async () => {
    setPreviewing(true)
    try {
      const res = await apiClient.post('/settings/email/template/preview', { template })
      setPreviewHtml(res.data.html)
      setMode('preview')
    } catch (err) {
      showError(err.message)
    } finally {
      setPreviewing(false)
    }
  }

  return (
    <FloatingWindow
      storageKey="email-template-editor"
      defaultPos={{ x: 120, y: 60, w: 900, h: 680 }}
      constraints={{ minW: 640, minH: 400 }}
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
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setMode('visual')}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                mode === 'visual' ? 'bg-accent-primary text-white' : 'text-text-secondary hover:bg-bg-tertiary'
              }`}
            >
              {t('settings.templateVisual')}
            </button>
            <button
              type="button"
              onClick={() => setMode('source')}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors flex items-center gap-1 ${
                mode === 'source' ? 'bg-accent-primary text-white' : 'text-text-secondary hover:bg-bg-tertiary'
              }`}
            >
              <Code size={14} /> HTML
            </button>
            <button
              type="button"
              onClick={handlePreview}
              disabled={previewing}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors flex items-center gap-1 ${
                mode === 'preview' ? 'bg-accent-primary text-white' : 'text-text-secondary hover:bg-bg-tertiary'
              }`}
            >
              {previewing ? <ArrowsClockwise size={14} className="animate-spin" /> : <Eye size={14} />}
              {t('settings.templatePreview')}
            </button>
          </div>
          <div className="flex items-center gap-1.5">
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

        {/* Variables hint */}
        <div className="flex items-start gap-2 px-3 py-2 bg-bg-tertiary/50 border-b border-border text-xs text-text-secondary">
          <Info size={14} className="shrink-0 mt-0.5 text-accent-primary" />
          <div className="flex flex-wrap gap-x-3 gap-y-0.5">
            {TEMPLATE_VARS.map(v => (
              <span key={v.var}>
                <code className="text-accent-primary font-mono text-[11px]">{v.var}</code>
                <span className="ml-1">{t(`settings.${v.desc}`)}</span>
              </span>
            ))}
          </div>
        </div>

        {/* Content area */}
        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center h-full text-text-tertiary">
              <ArrowsClockwise size={20} className="animate-spin" />
            </div>
          ) : mode === 'visual' ? (
            <EmailTemplateEditor content={template} onChange={handleChange} />
          ) : mode === 'source' ? (
            <textarea
              value={template}
              onChange={handleSourceChange}
              className="w-full h-full p-4 bg-bg-primary text-text-primary font-mono text-xs resize-none focus:outline-none"
              spellCheck={false}
            />
          ) : (
            <div className="h-full bg-white">
              <iframe
                srcDoc={previewHtml}
                title="Email Preview"
                className="w-full h-full border-0"
                sandbox="allow-same-origin"
              />
            </div>
          )}
        </div>
      </div>
    </FloatingWindow>
  )
}
