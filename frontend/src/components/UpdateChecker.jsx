/**
 * UpdateChecker Component - Check and install updates
 */
import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { ArrowsClockwise, Download, CheckCircle, Warning, Info, Rocket, ShieldCheck, ArrowCircleUp } from '@phosphor-icons/react'
import { Card, Button, Badge, LoadingSpinner, ServiceReconnectOverlay } from '../components'
import { apiClient } from '../services'
import { useNotification } from '../contexts'
import { useServiceReconnect, UPDATE_MAX_WAIT_MS } from '../hooks'
import { formatRelativeTime } from '../lib/utils'
import { MARKDOWN_ELEMENT_CLASSES } from '../lib/markdown'

export function UpdateChecker() {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [updateInfo, setUpdateInfo] = useState(null)
  const [error, setError] = useState(null)
  const [includePrereleases, setIncludePrereleases] = useState(false)
  const [includeChannel, setIncludeChannel] = useState('stable')
  const { showSuccess, showError, showConfirm } = useNotification()
  const { reconnecting, status, attempt, countdown, waitForRestart, cancel } = useServiceReconnect()

  const markdownClasses = "mt-3 p-3 bg-tertiary-op50 rounded-lg text-sm text-text-secondary max-h-64 overflow-y-auto prose prose-sm prose-invert max-w-none " + MARKDOWN_ELEMENT_CLASSES

  const checkForUpdates = async (showNotification = false, force = false) => {
    setChecking(true)
    setError(null)
    try {
      const params = `include_prereleases=${includeChannel !== 'stable'}&include_dev=${includeChannel === 'dev'}&force=${force}`
      const response = await apiClient.get(`/system/updates/check?${params}`)
      const data = response?.data || response || {}
      setUpdateInfo(data)
      if (showNotification) {
        if (data.update_available) {
          showSuccess(t('settings.updateAvailable', { version: data.latest_version }))
        } else {
          showSuccess(t('settings.upToDate'))
        }
      }
    } catch (err) {
      setError(err.message || t('settings.checkFailed', 'Failed to check for updates'))
      if (showNotification) {
        showError(t('settings.checkFailed', 'Failed to check for updates'))
      }
    } finally {
      setChecking(false)
      setLoading(false)
    }
  }

  const installUpdate = async () => {
    if (!updateInfo?.update_available) return
    
    const confirmed = await showConfirm(
      t('settings.installUpdateConfirm', { version: updateInfo.latest_version }),
      { title: t('settings.installUpdate'), confirmText: t('settings.installUpdate'), variant: 'primary' }
    )
    if (!confirmed) return

    setInstalling(true)
    try {
      await apiClient.post('/system/updates/install', {
        include_prereleases: includeChannel !== 'stable',
        include_dev: includeChannel === 'dev'
      })
      showSuccess(t('settings.updateInitiated', { version: updateInfo.latest_version, defaultValue: `Update to v${updateInfo.latest_version} initiated...` }))
      
      // Show reconnect overlay — countdown then poll until service is back
      waitForRestart({
        expectedVersion: updateInfo.latest_version,
        maxWaitMs: UPDATE_MAX_WAIT_MS
      })
    } catch (err) {
      showError(err.message || t('settings.installFailed', 'Failed to install update'))
      setInstalling(false)
    }
  }

  // A later major version: installed only on this explicit, confirmed request
  const installMajorUpgrade = async () => {
    const target = updateInfo?.major_upgrade
    if (!target) return
    const confirmed = await showConfirm(
      t('settings.majorUpgradeConfirm', { current: updateInfo.current_version, version: target.version }),
      { title: t('settings.majorUpgradeTitle', { version: target.version }), confirmText: t('settings.majorUpgradeInstall'), variant: 'primary' }
    )
    if (!confirmed) return

    setInstalling(true)
    try {
      await apiClient.post('/system/updates/install', { major_upgrade: true, version: target.version })
      showSuccess(t('settings.majorUpgradeInitiated', { version: target.version }))
      waitForRestart({ expectedVersion: target.version, maxWaitMs: UPDATE_MAX_WAIT_MS })
    } catch (err) {
      showError(err.message || t('settings.installFailed', 'Failed to install update'))
      setInstalling(false)
    }
  }

  const majorUpgrade = updateInfo?.major_upgrade || null

  const firstRender = React.useRef(true)
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      checkForUpdates()
    } else {
      setUpdateInfo(null)
      checkForUpdates(false, true)
    }
  }, [includeChannel])

  if (loading) {
    return (
      <Card className="p-4">
        <div className="flex items-center gap-3">
          <LoadingSpinner size="sm" />
          <span className="text-text-secondary">Checking for updates...</span>
        </div>
      </Card>
    )
  }

  return (
    <>
      {reconnecting && (
        <ServiceReconnectOverlay status={status} attempt={attempt} countdown={countdown} onCancel={cancel}
          note={t('reconnect.updateNote', { minutes: UPDATE_MAX_WAIT_MS / 60000 })} />
      )}
      <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className={`p-2 rounded-lg ${updateInfo?.update_available ? 'bg-accent-success-op15' : 'bg-bg-tertiary'}`}>
            {updateInfo?.update_available ? (
              <Rocket size={24} weight="duotone" className="text-accent-success" />
            ) : (
              <CheckCircle size={24} weight="duotone" className="text-text-secondary" />
            )}
          </div>
          
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-medium text-text-primary">
                {updateInfo?.update_available ? t('settings.updateAvailableTitle') : t('settings.upToDateTitle')}
              </h3>
              {updateInfo?.prerelease && (
                <Badge variant="warning" size="sm">{t('settings.prerelease')}</Badge>
              )}
            </div>
            
            <div className="text-sm text-text-secondary mt-1">
              {updateInfo?.update_available ? (
                <>
                  <span className="text-text-tertiary">{t('settings.current')}:</span> v{updateInfo.current_version}
                  <span className="mx-2">→</span>
                  <span className="text-accent-success font-medium">v{updateInfo.latest_version}</span>
                </>
              ) : (
                <>{t('common.running')} v{updateInfo?.current_version}</>
              )}
            </div>
            
            {updateInfo?.published_at && updateInfo?.update_available && (
              <div className="text-xs text-text-tertiary mt-1">
                Released {formatRelativeTime(updateInfo.published_at)}
              </div>
            )}
            
            {updateInfo?.update_available && !updateInfo?.can_auto_update && (
              <div className="text-xs text-text-tertiary mt-1">
                💡 docker pull ghcr.io/neyslim/ultimate-ca-manager:{updateInfo.latest_version}
              </div>
            )}
            
            {error && (
              <div className="flex items-center gap-1 text-accent-danger text-sm mt-2">
                <Warning size={14} />
                {error}
              </div>
            )}
            
            {updateInfo?.message && !updateInfo?.update_available && (
              <div className="flex items-center gap-1 text-text-tertiary text-xs mt-2">
                <Info size={14} />
                {updateInfo.message}
              </div>
            )}
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {updateInfo?.update_available && updateInfo?.can_auto_update && (
            <Button
              variant="primary"
              size="sm"
              onClick={installUpdate}
              disabled={installing || !updateInfo.download_url}
              className="gap-1.5"
            >
              {installing ? (
                <>
                  <LoadingSpinner size="xs" />
                  Installing...
                </>
              ) : (
                <>
                  <Download size={16} />
                  Install Update
                </>
              )}
            </Button>
          )}
          
          <Button
            variant="ghost"
            size="sm"
            onClick={() => checkForUpdates(true, true)}
            disabled={checking}
            className="gap-1.5"
          >
            <ArrowsClockwise size={16} className={checking ? 'animate-spin' : ''} />
            {checking ? t('settings.checking', 'Checking...') : t('settings.checkNow', 'Check Now')}
          </Button>
        </div>
      </div>
      
      {/* Security maintenance notice: comes from the check's data */}
      {updateInfo?.security_maintenance && (
        <div className="mt-4 flex items-start gap-2 p-2.5 bg-accent-warning-op10 rounded-lg text-xs text-text-secondary">
          <ShieldCheck size={16} className="shrink-0 mt-0.5 text-accent-warning" />
          <div>
            <div className="font-medium text-text-primary">{t('settings.securityMaintenanceTitle')}</div>
            <div>{t('settings.securityMaintenanceNotice')}</div>
            {majorUpgrade && (
              <div className="mt-1">{t('settings.securityMaintenanceUpgrade', { version: majorUpgrade.version })}</div>
            )}
          </div>
        </div>
      )}

      {/* Later major version: recommended, never installed automatically */}
      {majorUpgrade && (
        <div className="mt-4 p-3 rounded-lg border border-border bg-accent-primary-op5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <ArrowCircleUp size={22} weight="duotone" className="shrink-0 text-accent-primary" />
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="font-medium text-text-primary">{t('settings.majorUpgradeTitle', { version: majorUpgrade.version })}</h4>
                  <Badge variant="success" size="sm">{t('settings.majorUpgradeRecommended')}</Badge>
                </div>
                <p className="text-sm text-text-secondary mt-1">{t('settings.majorUpgradeDesc')}</p>
                {majorUpgrade.html_url && (
                  <a
                    href={majorUpgrade.html_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-accent-primary hover:underline"
                  >
                    {t('settings.majorUpgradeNotes')}
                  </a>
                )}
                {!updateInfo?.can_auto_update && (
                  <p className="text-xs text-text-tertiary mt-1">
                    {t('settings.majorUpgradeDocker', { image: `ghcr.io/neyslim/ultimate-ca-manager:${majorUpgrade.version}` })}
                  </p>
                )}
              </div>
            </div>
            {updateInfo?.can_auto_update && (
              <Button
                variant="secondary"
                size="sm"
                onClick={installMajorUpgrade}
                disabled={installing || !majorUpgrade.download_url}
                className="gap-1.5 shrink-0"
              >
                <ArrowCircleUp size={16} />
                {t('settings.majorUpgradeInstall')}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Release notes - current version */}
      {updateInfo?.current_release_notes && (
        <div className="mt-4 pt-4 border-t border-border-op50">
          <details className="group">
            <summary className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer hover:text-text-primary">
              <Info size={14} />
              {t('settings.currentReleaseNotes', { version: updateInfo.current_version })}
              {updateInfo.current_published_at && (
                <span className="text-xs text-text-tertiary ml-1">
                  ({formatRelativeTime(updateInfo.current_published_at)})
                </span>
              )}
            </summary>
            <div className={markdownClasses}>
              <ReactMarkdown>{updateInfo.current_release_notes}</ReactMarkdown>
            </div>
          </details>
        </div>
      )}
      
      {/* Release notes - available update */}
      {updateInfo?.update_available && updateInfo?.release_notes && (
        <div className="mt-4 pt-4 border-t border-border-op50">
          <details className="group" open>
            <summary className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer hover:text-text-primary">
              <Rocket size={14} className="text-success" />
              {t('settings.updateReleaseNotes', { version: updateInfo.latest_version })}
            </summary>
            <div className={markdownClasses}>
              <ReactMarkdown>{updateInfo.release_notes}</ReactMarkdown>
            </div>
          </details>
        </div>
      )}
      
      {/* Update channel */}
      <div className="mt-4 pt-4 border-t border-border-op50">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <label className="text-sm text-text-secondary whitespace-nowrap">{t('settings.updateChannel')}</label>
            <select
              value={includeChannel}
              onChange={(e) => setIncludeChannel(e.target.value)}
              className="text-sm bg-bg-secondary border border-border rounded-md px-2.5 py-1.5 text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-primary"
            >
              <option value="stable">{t('settings.channelStable')}</option>
              <option value="prerelease">{t('settings.channelPrerelease')}</option>
              <option value="dev">{t('settings.channelDev')}</option>
            </select>
          </div>
          
          {updateInfo?.html_url && (
            <a
              href={updateInfo.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-accent-primary hover:underline"
            >
              View on GitHub →
            </a>
          )}
        </div>
        
        {includeChannel === 'dev' && (
          <div className="flex items-start gap-2 mt-3 p-2.5 bg-accent-warning-op15 rounded-lg text-xs text-accent-warning">
            <Warning size={16} className="shrink-0 mt-0.5" />
            <span>{t('settings.channelDevWarning')}</span>
          </div>
        )}
      </div>
        </Card>
    </>
  )
}

export default UpdateChecker
