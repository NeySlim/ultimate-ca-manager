import { useTranslation } from 'react-i18next'
import { Palette, Desktop, Sun, Moon, Info } from '@phosphor-icons/react'
import {
  DetailContent, DetailHeader, DetailSection
} from '../../components'
import LanguageSelector from '../../components/ui/LanguageSelector'
import { useMobile } from '../../contexts'
import { useTheme } from '../../contexts/ThemeContext'

export default function AppearanceSettings() {
  const { t } = useTranslation()
  const { themeFamily, setThemeFamily, mode, setMode, themes } = useTheme()
  const { forceDesktop, setForceDesktop, screenWidth, breakpoints } = useMobile()
  
  const modeOptions = [
    { id: 'system', label: t('settings.followSystem'), icon: Desktop, description: t('settings.followSystemDesc') },
    { id: 'light', label: t('settings.light'), icon: Sun, description: t('settings.lightDesc') },
    { id: 'dark', label: t('settings.dark'), icon: Moon, description: t('settings.darkDesc') },
  ]
  
  return (
    <DetailContent>
      <DetailHeader
        icon={Palette}
        title={t('settings.tabs.appearance')}
        subtitle={t('settings.appearanceSubtitle')}
      />
      
      <DetailSection title={t('settings.colorTheme')}>
        <p className="text-sm text-text-secondary mb-4">
          {t('settings.colorThemeDesc')}
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {themes.map(theme => (
            <button
              key={theme.id}
              onClick={() => setThemeFamily(theme.id)}
              className={`
                p-4 rounded-lg border-2 transition-all text-left
                ${themeFamily === theme.id 
                  ? 'border-accent-primary bg-accent-primary-op10' 
                  : 'border-border hover:border-text-tertiary bg-tertiary-50'
                }
              `}
            >
              <div className="flex items-center gap-3 mb-2">
                <div 
                  className="w-5 h-5 rounded-full shadow-inner"
                  style={{ background: theme.accent }}
                />
                <span className="font-medium text-sm text-text-primary">{theme.name}</span>
              </div>
              <div className="flex gap-1">
                {/* Preview colors - show accent and distinct bg colors */}
                <div className="w-6 h-3 rounded-sm" style={{ background: theme.accent }} />
                <div className="w-6 h-3 rounded-sm" style={{ background: theme.dark['bg-tertiary'] }} />
                <div className="w-6 h-3 rounded-sm" style={{ background: theme.light['bg-tertiary'] }} />
                <div className="w-6 h-3 rounded-sm" style={{ background: theme.light['accent-primary'] || theme.accent }} />
              </div>
            </button>
          ))}
        </div>
      </DetailSection>
      
      <DetailSection title={t('settings.appearanceMode')}>
        <p className="text-sm text-text-secondary mb-4">
          {t('settings.appearanceModeDesc')}
        </p>
        <div className="space-y-2">
          {modeOptions.map(opt => {
            const Icon = opt.icon
            return (
              <button
                key={opt.id}
                onClick={() => setMode(opt.id)}
                className={`
                  w-full p-4 rounded-lg border-2 transition-all text-left flex items-center gap-4
                  ${mode === opt.id 
                    ? 'border-accent-primary bg-accent-primary-op10' 
                    : 'border-border hover:border-text-tertiary bg-tertiary-50'
                  }
                `}
              >
                <div className={`
                  w-10 h-10 rounded-lg flex items-center justify-center
                  ${mode === opt.id ? 'bg-accent-primary text-white' : 'bg-bg-secondary text-text-secondary'}
                `}>
                  <Icon size={20} weight={mode === opt.id ? 'fill' : 'regular'} />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-text-primary">{opt.label}</div>
                  <div className="text-xs text-text-tertiary">{opt.description}</div>
                </div>
                {mode === opt.id && (
                  <div className="w-5 h-5 rounded-full bg-accent-primary flex items-center justify-center">
                    <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                )}
              </button>
            )
          })}
        </div>
      </DetailSection>
      
      <DetailSection title={t('settings.layoutMode')}>
        <p className="text-sm text-text-secondary mb-4">
          {t('settings.layoutModeDesc')}
        </p>
        <button
          onClick={() => setForceDesktop(!forceDesktop)}
          className={`
            w-full p-4 rounded-lg border-2 transition-all text-left flex items-center gap-4
            ${forceDesktop 
              ? 'border-accent-primary bg-accent-primary-op10' 
              : 'border-border hover:border-text-tertiary bg-tertiary-50'
            }
          `}
        >
          <div className={`
            w-10 h-10 rounded-lg flex items-center justify-center
            ${forceDesktop ? 'bg-accent-primary text-white' : 'bg-bg-secondary text-text-secondary'}
          `}>
            <Desktop size={20} weight={forceDesktop ? 'fill' : 'regular'} />
          </div>
          <div className="flex-1">
            <div className="font-medium text-text-primary">{t('settings.forceDesktopLayout')}</div>
            <div className="text-xs text-text-tertiary">
              {forceDesktop 
                ? t('settings.desktopLayoutEnabled') 
                : t('settings.mobileLayoutActivates', { breakpoint: breakpoints.lg, current: screenWidth })
              }
            </div>
          </div>
          <div className={`
            w-12 h-6 rounded-full transition-colors relative
            ${forceDesktop ? 'bg-accent-primary' : 'bg-bg-secondary border border-border'}
          `}>
            <div className={`
              absolute top-1 w-4 h-4 rounded-full transition-transform
              ${forceDesktop 
                ? 'bg-white translate-x-6' 
                : 'bg-text-tertiary translate-x-1'
              }
            `} />
          </div>
        </button>
        {forceDesktop && (
          <p className="text-xs text-text-tertiary mt-2 flex items-center gap-1">
            <Info size={12} />
            {t('settings.settingSavedInBrowser')}
          </p>
        )}
      </DetailSection>
      
      <DetailSection title={t('settings.language')}>
        <p className="text-sm text-text-secondary mb-4">
          {t('settings.languageDesc')}
        </p>
        <LanguageSelector />
      </DetailSection>
      
      <DetailSection title={t('settings.preview')}>
        <div className="p-4 rounded-lg bg-bg-tertiary border border-border">
          <p className="text-sm text-text-secondary mb-2">{t('settings.currentSettings')}:</p>
          <p className="text-text-primary">
            <span className="font-medium">{themes.find(th => th.id === themeFamily)?.name}</span>
            {' · '}
            <span className="text-text-secondary">
              {mode === 'system' ? t('settings.followingSystemPreference') : mode === 'dark' ? t('settings.darkMode') : t('settings.lightMode')}
            </span>
            {forceDesktop && (
              <>
                {' · '}
                <span className="text-accent-primary">{t('settings.desktopForced')}</span>
              </>
            )}
          </p>
        </div>
      </DetailSection>
    </DetailContent>
  )
}
