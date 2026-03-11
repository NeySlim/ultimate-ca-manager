/**
 * UpdateChecker Component - Check and install updates
 */
import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { ArrowsClockwise, Download, CheckCircle, Warning, Info, Rocket } from '@phosphor-icons/react'
import { Card, Button, Badge, LoadingSpinner, ServiceReconnectOverlay } from '../components'
import { apiClient } from '../services'
import { useNotification } from '../contexts'
import { useServiceReconnect } from '../hooks'
import { formatRelativeTime } from '../lib/ui'

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

  const checkForUpdates = async (showNotification = false, force = false) => {
    setChecking(true)
    setError(null)
    try {
      const params = `include_prereleases=${includeChannel !== 'stable'}&include_dev=${includeChannel === 'dev'}&force=${force}`
      const response = await apiClient.get(`/system/updates/check?${params}`)
      setUpdateInfo(response.data)
      if (showNotification) {
        if (response.data.update_available) {
          showSuccess(t('settings.updateAvailable', { version: response.data.latest_version }))
        } else {
          showSuccess(t('settings.upToDate'))
        }
      }
    } catch (err) {
      setError(err.message || 'Failed to check for updates')
      if (showNotification) {
        showError('Failed to check for updates')
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
      showSuccess(`Update to v${updateInfo.latest_version} initiated...`)
      
      // Show reconnect overlay — countdown then poll until service is back
      waitForRestart({
        expectedVersion: updateInfo.latest_version
      })
    } catch (err) {
      showError(err.message || 'Failed to install update')
      setInstalling(false)
    }
  }

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
        <ServiceReconnectOverlay status={status} attempt={attempt} countdown={countdown} onCancel={cancel} />
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
                💡 docker pull ghcr.io/neyslim/ultimate-ca-manager:latest
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
            {checking ? 'Checking...' : 'Check Now'}
          </Button>
        </div>
      </div>
      
      {/* Release notes */}
      {updateInfo?.update_available && updateInfo?.release_notes && (
        <div className="mt-4 pt-4 border-t border-border-op50">
          <details className="group">
            <summary className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer hover:text-text-primary">
              <Info size={14} />
              {t('settings.viewReleaseNotes')}
            </summary>
            <div className="mt-3 p-3 bg-tertiary-op50 rounded-lg text-sm text-text-secondary max-h-64 overflow-y-auto prose prose-sm prose-invert max-w-none
              [&_h1]:text-base [&_h1]:font-semibold [&_h1]:text-text-primary [&_h1]:mt-3 [&_h1]:mb-1
              [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:text-text-primary [&_h2]:mt-3 [&_h2]:mb-1
              [&_h3]:text-xs [&_h3]:font-semibold [&_h3]:text-text-primary [&_h3]:mt-2 [&_h3]:mb-1
              [&_ul]:list-disc [&_ul]:pl-4 [&_ul]:my-1
              [&_ol]:list-decimal [&_ol]:pl-4 [&_ol]:my-1
              [&_li]:my-0.5 [&_li]:text-text-secondary
              [&_strong]:text-text-primary [&_strong]:font-semibold
              [&_code]:text-accent-primary [&_code]:bg-bg-tertiary [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs
              [&_p]:my-1
              [&_a]:text-accent-primary [&_a]:underline
              [&_hr]:border-border [&_hr]:my-2
            ">
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
