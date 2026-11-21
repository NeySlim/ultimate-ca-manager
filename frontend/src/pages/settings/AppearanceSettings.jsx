/**
 * Appearance and language of this browser: theme family and mode as the mockup's segmented
 * choices, the desktop layout as a check line, the language, and what is in force.
 */
import { useTranslation } from 'react-i18next'
import { Props } from '../../components/atelier'
import { Select, ToggleSwitch, SegmentedField } from '../../components/atelier/Form'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { chooseLanguage } from '../../lib/chooseLanguage'
import { languages } from '../../i18n'
import { useMobile } from '../../contexts'
import { useTheme } from '../../contexts/ThemeContext'

export default function AppearanceSettings() {
  const { t, i18n } = useTranslation()
  const { themeFamily, setThemeFamily, mode, setMode, themes } = useTheme()
  const { forceDesktop, setForceDesktop, screenWidth, breakpoints } = useMobile()

  const modeOptions = [
    { value: 'system', label: t('settings.followSystem'), description: t('settings.followSystemDesc') },
    { value: 'light', label: t('settings.light'), description: t('settings.lightDesc') },
    { value: 'dark', label: t('settings.dark'), description: t('settings.darkDesc') },
  ]
  const currentMode = modeOptions.find((o) => o.value === mode)
  const family = themes.find((th) => th.id === themeFamily)

  return (
    <>
      <SettingsGroup legend={t('settings.theme')} hint={t('settings.colorThemeDesc')}>
        {/* The theme's own accent is a value of the theme, shown as its swatch */}
        <SegmentedField id="set-theme_family" label={t('settings.colorTheme')}
          options={themes.map((theme) => ({
            value: theme.id,
            label: <><span className="swatch" style={{ background: theme.accent }} aria-hidden="true" />{t(theme.nameKey)}</>,
          }))}
          pressed={(id) => themeFamily === id} onPick={setThemeFamily} />
        <SegmentedField id="set-theme_mode" label={t('settings.appearanceMode')} hint={currentMode?.description}
          options={modeOptions} pressed={(value) => mode === value} onPick={setMode} />
      </SettingsGroup>

      <SettingsGroup legend={t('settings.layoutMode')} hint={t('settings.layoutModeDesc')}>
        <ToggleSwitch id="set-force_desktop" checked={forceDesktop} onChange={(on) => setForceDesktop(on)} label={t('settings.forceDesktopLayout')}
          description={forceDesktop
            ? t('settings.desktopLayoutEnabled')
            : t('settings.mobileLayoutActivates', { breakpoint: breakpoints.lg, current: screenWidth })} />
      </SettingsGroup>

      <SettingsGroup legend={t('settings.language')} hint={t('settings.languageDesc')}>
        <Select id="set-language" label={t('settings.language')} value={i18n.language?.split('-')[0] || 'en'}
          onChange={(code) => chooseLanguage(i18n, code)} options={languages.map((lang) => ({ value: lang.code, label: lang.name }))} />
      </SettingsGroup>

      <SettingsGroup legend={t('settings.preview')} grid={false}>
        <Props items={[[t('settings.currentSettings'), (
          <>
            {t(family?.nameKey)}
            {' · '}
            {mode === 'system' ? t('settings.followingSystemPreference') : mode === 'dark' ? t('settings.darkMode') : t('settings.lightMode')}
            {forceDesktop && <>{' · '}{t('settings.desktopForced')}</>}
          </>
        )]]} />
        {forceDesktop && <p className="group-hint">{t('settings.settingSavedInBrowser')}</p>}
      </SettingsGroup>
    </>
  )
}
