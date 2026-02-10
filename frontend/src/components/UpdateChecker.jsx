/**
 * UpdateChecker Component - Check and install updates
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowsClockwise, Download, CheckCircle, Warning, Info, Rocket } from '@phosphor-icons/react'
import { Card, Button, Badge, LoadingSpinner } from '../components'
import { apiClient } from '../services'
import { useNotification } from '../contexts'
import { formatRelativeTime } from '../lib/ui'

export function UpdateChecker() {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [updateInfo, setUpdateInfo] = useState(null)
  const [error, setError] = useState(null)
  const [includePrereleases, setIncludePrereleases] = useState(false)
  const { showSuccess, showError } = useNotification()

  const checkForUpdates = async (showNotification = false) => {
    setChecking(true)
    setError(null)
    try {
      const response = await apiClient.get(`/system/updates/check?include_prereleases=${includePrereleases}`)
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
    
    if (!confirm(`Install update v${updateInfo.latest_version}?\n\nThe service will restart and you may need to log in again.`)) {
      return
    }

    setInstalling(true)
    try {
      await apiClient.post('/system/updates/install', {
        include_prereleases: includePrereleases
      })
      showSuccess(`Update to v${updateInfo.latest_version} initiated. Page will reload shortly...`)
      
      // Wait and reload
      setTimeout(() => {
        window.location.reload()
      }, 10000)
    } catch (err) {
      showError(err.message || 'Failed to install update')
      setInstalling(false)
    }
  }

  useEffect(() => {
    checkForUpdates()
  }, [includePrereleases])

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
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className={`p-2 rounded-lg ${updateInfo?.update_available ? 'bg-accent-success/15' : 'bg-bg-tertiary'}`}>
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
            onClick={() => checkForUpdates(true)}
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
        <div className="mt-4 pt-4 border-t border-border/50">
          <details className="group">
            <summary className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer hover:text-text-primary">
              <Info size={14} />
              View Release Notes
            </summary>
            <div className="mt-3 p-3 bg-bg-tertiary/50 rounded-lg text-sm text-text-secondary whitespace-pre-wrap max-h-48 overflow-y-auto">
              {updateInfo.release_notes}
            </div>
          </details>
        </div>
      )}
      
      {/* Options */}
      <div className="mt-4 pt-4 border-t border-border/50 flex items-center gap-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={includePrereleases}
            onChange={(e) => setIncludePrereleases(e.target.checked)}
            className="rounded border-border"
          />
          <span className="text-text-secondary">Include pre-release versions</span>
        </label>
        
        {updateInfo?.html_url && (
          <a
            href={updateInfo.html_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-accent-primary hover:underline ml-auto"
          >
            View on GitHub →
          </a>
        )}
      </div>
    </Card>
  )
}

export default UpdateChecker
