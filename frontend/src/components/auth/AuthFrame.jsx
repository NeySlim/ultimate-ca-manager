/**
 * Frame of the pages shown before sign-in: a skip link, theme and language at the top right,
 * one card (brand, title, lead, content), version and project link below.
 */
import { forwardRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Warning } from '@phosphor-icons/react'
import { Logo } from '../Logo'
import { ThemeMenu } from '../shell/ThemeMenu'
import { AuthLanguageMenu } from './AuthLanguageMenu'
import './auth.css'

export const PROJECT_URL = 'https://github.com/NeySlim/ultimate-ca-manager'

export const AuthFrame = forwardRef(function AuthFrame({ title, lead, children, tools = true, footer = true }, titleRef) {
  const { t } = useTranslation()
  // The tab names the screen while it shows, then gives the console its title back
  useEffect(() => {
    if (typeof title !== 'string' || !title) return undefined
    const before = document.title
    document.title = `${title} · UCM`
    return () => { document.title = before }
  }, [title])
  const skip = (e) => {
    e.preventDefault()
    document.getElementById('main')?.focus()
  }
  return (
    <div className="auth-page">
      <a className="auth-skip" href="#main" onClick={skip}>{t('auth.page.skipToContent')}</a>
      <main className="auth" id="main" tabIndex={-1}>
        {tools && (
          <div className="auth-tools">
            <AuthLanguageMenu />
            <ThemeMenu />
          </div>
        )}
        <section className="auth-card" aria-labelledby="auth-title">
          <div className="auth-brand">
            <Logo variant="icon" withText={false} size="md" />
            <strong>UCM</strong>
          </div>
          <h1 id="auth-title" ref={titleRef} tabIndex={-1}>{title}</h1>
          {lead && <p className="auth-lead">{lead}</p>}
          {children}
        </section>
        {footer && (
          <footer className="auth-foot">
            <span>UCM {typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : ''}</span>
            <a className="auth-link" href={PROJECT_URL} target="_blank" rel="noopener noreferrer">
              GitHub
            </a>
          </footer>
        )}
      </main>
    </div>
  )
})

/** A labelled field of the frame; `error` is announced through aria-describedby. */
export function AuthField({ id, label, error, children }) {
  return (
    <div className="auth-field">
      <label htmlFor={id}>{label}</label>
      {children}
      {error && <FieldError id={`${id}-error`}>{error}</FieldError>}
    </div>
  )
}

function FieldError({ id, children }) {
  return <p className="auth-field-error" id={id}><Warning size={13} aria-hidden="true" /><span>{children}</span></p>
}
