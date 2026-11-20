/**
 * Appearance and language of this browser: theme family and mode as the mockup's segmented
 * choices, the desktop layout as a check line, the language, and what is in force.
 */
import { useTranslation } from 'react-i18next'
import { Desktop, Sun, Moon, Info } from '@phosphor-icons/react'

import LanguageSelector from '../../components/ui/LanguageSelector'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { useMobile } from '../../contexts'
import { useTheme } from '../../contexts/ThemeContext'
import { FormGroup } from '../../components/sectioned'

export default function AppearanceSettings() {
  const { t } = useTranslation()
  const { themeFamily, setThemeFamily, mode, setMode, themes } = useTheme()
  const { forceDesktop, setForceDesktop, screenWidth, breakpoints } = useMobile()

  const modeOptions = [
    { id: 'system', label: t('settings.followSystem'), icon: Desktop, description: t('settings.followSystemDesc') },
    { id: 'light', label: t('settings.light'), icon: Sun, description: t('settings.lightDesc') },
    { id: 'dark', label: t('settings.dark'), icon: Moon, description: t('settings.darkDesc') },
  ]
  const currentMode = modeOptions.find((o) => o.id === mode)

  return (
    <>
      <FormGroup title={t('settings.colorTheme')} description={t('settings.colorThemeDesc')}>
        <div className="ui-segmented" role="group" aria-label={t('settings.colorTheme')}>
          {themes.map((theme) => (
            <button key={theme.id} type="button" aria-pressed={themeFamily === theme.id} onClick={() => setThemeFamily(theme.id)}>
              <span className="sf-swatch" style={{ background: theme.accent }} aria-hidden="true" />
              {t(theme.nameKey)}
            </button>
          ))}
        </div>
      </FormGroup>

      <FormGroup title={t('settings.appearanceMode')} description={t('settings.appearanceModeDesc')}>
        <div className="ui-segmented" role="group" aria-label={t('settings.appearanceMode')}>
          {modeOptions.map((opt) => {
            const Icon = opt.icon
            return (
              <button key={opt.id} type="button" aria-pressed={mode === opt.id} onClick={() => setMode(opt.id)}>
                <Icon size={14} aria-hidden="true" />
                {opt.label}
              </button>
            )
          })}
        </div>
        {currentMode && <p className="sf-hint sf-under">{currentMode.description}</p>}
      </FormGroup>

      <FormGroup title={t('settings.layoutMode')} description={t('settings.layoutModeDesc')}>
        <ToggleSwitch
          checked={forceDesktop}
          onChange={(on) => setForceDesktop(on)}
          label={t('settings.forceDesktopLayout')}
          description={forceDesktop
            ? t('settings.desktopLayoutEnabled')
            : t('settings.mobileLayoutActivates', { breakpoint: breakpoints.lg, current: screenWidth })}
        />
      </FormGroup>

      <FormGroup title={t('settings.language')} description={t('settings.languageDesc')}>
        <LanguageSelector />
      </FormGroup>

      <FormGroup title={t('settings.preview')}>
        <dl className="sf-props">
          <dt>{t('settings.currentSettings')}</dt>
          <dd>
            {t(themes.find((th) => th.id === themeFamily)?.nameKey)}
            {' · '}
            {mode === 'system' ? t('settings.followingSystemPreference') : mode === 'dark' ? t('settings.darkMode') : t('settings.lightMode')}
            {forceDesktop && <>{' · '}{t('settings.desktopForced')}</>}
          </dd>
        </dl>
        {forceDesktop && (
          <p className="sf-hint sf-under"><Info size={12} aria-hidden="true" /> {t('settings.settingSavedInBrowser')}</p>
        )}
      </FormGroup>
    </>
  )
}
