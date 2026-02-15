/**
 * EmailTemplateWindow — Floating window with split-pane email template editor
 * 
 * Features:
 * - Two tabs: HTML template + Plain Text template
 * - Split pane: source editor (left) + live preview (right)
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
  ArrowsClockwise, Info, Code, TextT
} from '@phosphor-icons/react'
import { apiClient } from '../services/apiClient'
import { useNotification } from '../contexts/NotificationContext'

const HTML_VARS = [
  { var: '{{logo}}', desc: 'templateVarLogo' },
  { var: '{{title}}', desc: 'templateVarTitle' },
  { var: '{{title_color}}', desc: 'templateVarTitleColor' },
  { var: '{{content}}', desc: 'templateVarContent' },
  { var: '{{datetime}}', desc: 'templateVarDatetime' },
  { var: '{{instance_url}}', desc: 'templateVarInstanceUrl' },
]

const TEXT_VARS = [
  { var: '{{title}}', desc: 'templateVarTitle' },
  { var: '{{content}}', desc: 'templateVarContent' },
  { var: '{{datetime}}', desc: 'templateVarDatetime' },
  { var: '{{instance_url}}', desc: 'templateVarInstanceUrl' },
]

export default function EmailTemplateWindow({ onClose }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  
  const [tab, setTab] = useState('html') // html, text
  const [htmlTemplate, setHtmlTemplate] = useState('')
  const [textTemplate, setTextTemplate] = useState('')
  const [defaultHtml, setDefaultHtml] = useState('')
  const [defaultText, setDefaultText] = useState('')
  const [isHtmlCustom, setIsHtmlCustom] = useState(false)
  const [isTextCustom, setIsTextCustom] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewText, setPreviewText] = useState('')
  const [dirty, setDirty] = useState(false)
  const previewTimer = useRef(null)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiClient.get('/settings/email/template')
        setHtmlTemplate(res.data.template)
        setTextTemplate(res.data.text_template)
        setDefaultHtml(res.data.default_template)
        setDefaultText(res.data.default_text_template)
        setIsHtmlCustom(res.data.is_custom)
        setIsTextCustom(res.data.is_text_custom)
        // Initial previews
        const [htmlPrev, textPrev] = await Promise.all([
          apiClient.post('/settings/email/template/preview', { template: res.data.template, type: 'html' }),
          apiClient.post('/settings/email/template/preview', { template: res.data.text_template, type: 'text' }),
        ])
        setPreviewHtml(htmlPrev.data.html)
        setPreviewText(textPrev.data.text)
      } catch (err) {
        showError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
    return () => { if (previewTimer.current) clearTimeout(previewTimer.current) }
  }, [])

  const refreshPreview = useCallback((value, type) => {
    if (previewTimer.current) clearTimeout(previewTimer.current)
    previewTimer.current = setTimeout(async () => {
      try {
        const res = await apiClient.post('/settings/email/template/preview', { template: value, type })
        if (type === 'text') setPreviewText(res.data.text)
        else setPreviewHtml(res.data.html)
      } catch {
        // Silently fail during typing
      }
    }, 800)
  }, [])

  const handleHtmlChange = useCallback((e) => {
    setHtmlTemplate(e.target.value)
    setDirty(true)
    refreshPreview(e.target.value, 'html')
  }, [refreshPreview])

  const handleTextChange = useCallback((e) => {
    setTextTemplate(e.target.value)
    setDirty(true)
    refreshPreview(e.target.value, 'text')
  }, [refreshPreview])

  const handleSave = async () => {
    setSaving(true)
    try {
      await apiClient.patch('/settings/email/template', {
        template: htmlTemplate,
        text_template: textTemplate
      })
      setIsHtmlCustom(true)
      setIsTextCustom(true)
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
      setHtmlTemplate(defaultHtml)
      setTextTemplate(defaultText)
      setIsHtmlCustom(false)
      setIsTextCustom(false)
      setDirty(false)
      refreshPreview(defaultHtml, 'html')
      refreshPreview(defaultText, 'text')
      showSuccess(t('settings.templateResetSuccess'))
    } catch (err) {
      showError(err.message)
    }
  }

  const isCustom = tab === 'html' ? isHtmlCustom : isTextCustom
  const vars = tab === 'html' ? HTML_VARS : TEXT_VARS

  return (
    <FloatingWindow
      storageKey="email-template-editor"
      defaultPos={{ x: 60, y: 30, w: 1300, h: 720 }}
      constraints={{ minW: 800, maxW: 1800, minH: 400 }}
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
          <div className="flex items-center gap-3">
            {/* Tab switcher */}
            <div className="flex items-center gap-1 bg-bg-tertiary rounded-md p-0.5">
              <button type="button" onClick={() => setTab('html')}
                className={`px-2.5 py-1 text-xs rounded transition-colors flex items-center gap-1.5 ${
                  tab === 'html' ? 'bg-accent-primary text-white shadow-sm' : 'text-text-secondary hover:text-text-primary'}`}>
                <Code size={14} /> HTML
              </button>
              <button type="button" onClick={() => setTab('text')}
                className={`px-2.5 py-1 text-xs rounded transition-colors flex items-center gap-1.5 ${
                  tab === 'text' ? 'bg-accent-primary text-white shadow-sm' : 'text-text-secondary hover:text-text-primary'}`}>
                <TextT size={14} /> {t('settings.templatePlainText')}
              </button>
            </div>
            {/* Variables */}
            <div className="flex items-start gap-1.5 min-w-0">
              <Info size={12} className="shrink-0 mt-0.5 text-accent-primary" />
              <div className="flex flex-wrap gap-x-2.5 gap-y-0.5 text-[11px] text-text-tertiary">
                {vars.map(v => (
                  <span key={v.var}>
                    <code className="text-accent-primary font-mono">{v.var}</code>
                    <span className="ml-0.5">{t(`settings.${v.desc}`)}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {(isHtmlCustom || isTextCustom) && (
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

        {/* Split pane */}
        <div className="flex-1 flex min-h-0">
          {loading ? (
            <div className="flex items-center justify-center w-full text-text-tertiary">
              <ArrowsClockwise size={20} className="animate-spin" />
            </div>
          ) : (
            <>
              <div className="w-1/2 flex flex-col border-r border-border min-h-0">
                <div className="px-3 py-1.5 bg-bg-tertiary border-b border-border text-[11px] font-medium text-text-tertiary uppercase tracking-wider">
                  {tab === 'html' ? 'HTML Source' : t('settings.templatePlainText')}
                </div>
                <textarea
                  value={tab === 'html' ? htmlTemplate : textTemplate}
                  onChange={tab === 'html' ? handleHtmlChange : handleTextChange}
                  className="flex-1 w-full p-3 bg-bg-primary text-text-primary font-mono text-[12px] leading-[1.6] resize-none focus:outline-none"
                  spellCheck={false}
                />
              </div>
              <div className="w-1/2 flex flex-col min-h-0">
                <div className="px-3 py-1.5 bg-bg-tertiary border-b border-border text-[11px] font-medium text-text-tertiary uppercase tracking-wider">
                  {t('settings.templatePreview')}
                </div>
                {tab === 'html' ? (
                  <div className="flex-1 overflow-auto bg-[#f4f5f7]">
                    <iframe srcDoc={previewHtml} title="Email Preview"
                      className="w-full h-full border-0" sandbox="allow-same-origin" style={{ minHeight: '100%' }} />
                  </div>
                ) : (
                  <div className="flex-1 overflow-auto bg-bg-primary p-4">
                    <pre className="text-text-primary text-xs font-mono whitespace-pre-wrap leading-[1.6]">{previewText}</pre>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </FloatingWindow>
  )
}
