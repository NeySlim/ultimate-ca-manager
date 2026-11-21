/**
 * The email template editor in the mockup's wide modal(): the format (HTML or plain text) in a
 * segmented switch, its variables in a notice, the source beside its live preview, then Reset
 * (a custom template only), Close and Save.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from '../../components/atelier/AtelierDialog'
import { Btn } from '../../components/atelier/Btn'
import { Toolbar } from '../../components/atelier/Toolbar'
import { Field, ModalActions, Notice } from '../../components/atelier/Form'
import { SkeletonPanel } from '../../components/atelier/Skeleton'
import { apiClient } from '../../services/apiClient'
import { useNotification } from '../../contexts/NotificationContext'

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

export default function EmailTemplateDialog({ onClose }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const [tab, setTab] = useState('html')
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
    // A request still in flight when the dialog closes writes nothing and raises no toast
    let cancelled = false
    const load = async () => {
      try {
        const res = await apiClient.get('/settings/email/template')
        if (cancelled) return
        setHtmlTemplate(res.data.template)
        setTextTemplate(res.data.text_template)
        setDefaultHtml(res.data.default_template)
        setDefaultText(res.data.default_text_template)
        setIsHtmlCustom(res.data.is_custom)
        setIsTextCustom(res.data.is_text_custom)
        const [htmlPrev, textPrev] = await Promise.all([
          apiClient.post('/settings/email/template/preview', { template: res.data.template, type: 'html' }),
          apiClient.post('/settings/email/template/preview', { template: res.data.text_template, type: 'text' }),
        ])
        if (cancelled) return
        setPreviewHtml(htmlPrev.data.html)
        setPreviewText(textPrev.data.text)
      } catch (err) {
        if (cancelled) return
        showError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
      if (previewTimer.current) clearTimeout(previewTimer.current)
    }
  }, [])

  const refreshPreview = useCallback((value, type) => {
    if (previewTimer.current) clearTimeout(previewTimer.current)
    previewTimer.current = setTimeout(async () => {
      try {
        const res = await apiClient.post('/settings/email/template/preview', { template: value, type })
        if (type === 'text') setPreviewText(res.data.text)
        else setPreviewHtml(res.data.html)
      } catch {
        // a preview that fails while typing keeps the last one
      }
    }, 800)
  }, [])

  const onSource = (e) => {
    const value = e.target.value
    if (tab === 'html') setHtmlTemplate(value)
    else setTextTemplate(value)
    setDirty(true)
    refreshPreview(value, tab)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await apiClient.patch('/settings/email/template', { template: htmlTemplate, text_template: textTemplate })
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
    const confirmed = await showConfirm(t('settings.templateResetConfirm'), {
      title: t('common.reset', 'Reset'),
      confirmText: t('common.reset', 'Reset'),
      variant: 'danger',
    })
    if (!confirmed) return
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

  const html = tab === 'html'
  const isCustom = html ? isHtmlCustom : isTextCustom
  const vars = html ? HTML_VARS : TEXT_VARS

  return (
    <AtelierDialog title={t('settings.emailTemplate')} subtitle={isCustom ? t('settings.templateCustom') : t('settings.templateDefault')}
      size="wide" onClose={onClose} testId="email-template-dialog">
      <Toolbar>
        <div className="segmented" role="group" aria-label={t('settings.templateFormat')}>
          <button type="button" aria-pressed={html} onClick={() => setTab('html')}>HTML</button>
          <button type="button" aria-pressed={!html} onClick={() => setTab('text')}>{t('settings.templatePlainText')}</button>
        </div>
      </Toolbar>
      <Notice>
        {t('settings.templateVariablesLead')}
        {vars.map((v, i) => <span key={v.var}>{i > 0 && ', '}<span className="mono">{v.var}</span> {t(`settings.${v.desc}`)}</span>)}
      </Notice>
      {loading ? <SkeletonPanel label={t('common.loading')} /> : (
        <div className="form-fields">
          <Field id="template-source" label={html ? t('settings.templateHtmlSource') : t('settings.templatePlainText')}>
            <textarea id="template-source" className="mono template-source" spellCheck={false}
              value={html ? htmlTemplate : textTemplate} onChange={onSource} />
          </Field>
          <div className="field">
            <span>{t('settings.templatePreview')}</span>
            {html
              ? <iframe className="template-preview" srcDoc={previewHtml} title={t('settings.templatePreview')} sandbox="" />
              : <pre className="code-preview template-preview">{previewText}</pre>}
          </div>
        </div>
      )}
      <ModalActions>
        {(isHtmlCustom || isTextCustom) && <Btn icon="refresh" write onClick={handleReset}>{t('settings.templateResetDefault')}</Btn>}
        <Btn onClick={onClose}>{t('common.close')}</Btn>
        <Btn tone="primary" icon="check" onClick={handleSave} disabled={saving || !dirty}>{t('common.save')}</Btn>
      </ModalActions>
    </AtelierDialog>
  )
}
