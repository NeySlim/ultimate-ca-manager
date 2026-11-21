/**
 * The mockup's authPage(): the skip link, `#app.auth-mode > main.auth` with the tools at the top
 * right (language, theme), one `.auth-card` (brand, title, lead, content) and `.auth-foot`, drawn
 * by styles/atelier/maquette.css under `.atl`. Every page shown before sign-in uses it.
 */
import { forwardRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { LogoIcon } from '../Logo'
import { ThemeMenu } from '../shell/ThemeMenu'
import { FieldError } from '../atelier/SettingsView'
import { AtlScopeContext } from '../atelier/scope'
import { AuthLanguageMenu } from './AuthLanguageMenu'
import { useThemeColor } from '../../lib/themeColor'
import '../../styles/atelier/scope.css'
import '../../styles/atelier/maquette.css'
import '../../styles/atelier/extensions.css'

export const PROJECT_URL = 'https://github.com/NeySlim/ultimate-ca-manager'

export const AuthFrame = forwardRef(function AuthFrame({ title, lead, children, tools = true, footer = true }, titleRef) {
  const { t } = useTranslation()
  useThemeColor()
  // The tab names the screen while it shows, then gives the console its title back
  useEffect(() => {
    if (typeof title !== 'string' || !title) return undefined
    const before = document.title
    document.title = `${title} · UCM`
    return () => { document.title = before }
  }, [title])
  // The skip link moves the focus without writing #main in the address (a launch window reads its hash)
  const skip = (e) => {
    e.preventDefault()
    document.getElementById('main')?.focus()
  }
  return (
    <div className="atl atl-auth">
      <AtlScopeContext.Provider value>
        <a className="skip" href="#main" onClick={skip}>{t('auth.page.skipToContent')}</a>
        <div id="app" className="auth-mode">
          <main className="auth" id="main" tabIndex={-1}>
            {tools && (
              <div className="auth-tools">
                <AuthLanguageMenu />
                <ThemeMenu />
              </div>
            )}
            <section className="auth-card" aria-labelledby="main-title">
              <div className="auth-brand"><LogoIcon size={30} /><strong>UCM</strong></div>
              <h1 id="main-title" ref={titleRef} tabIndex={-1}>{title}</h1>
              {lead && <p className="auth-lead">{lead}</p>}
              {children}
            </section>
            {footer && (
              <footer className="auth-foot">
                <span>UCM {typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : ''}</span>
                <a className="text-link" href={PROJECT_URL} target="_blank" rel="noopener noreferrer">GitHub</a>
              </footer>
            )}
          </main>
        </div>
      </AtlScopeContext.Provider>
    </div>
  )
})

/** `.field`: label, control, and the mockup's authFieldError() (`err-<id>`, read through aria-describedby). */
export function AuthField({ id, label, error, children }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {error && <FieldError id={`err-${id}`} message={error} />}
    </div>
  )
}
