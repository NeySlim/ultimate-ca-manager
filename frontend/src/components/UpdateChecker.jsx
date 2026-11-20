/**
 * UpdateChecker Component - Check and install updates
 */
import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { ArrowsClockwise, Download, Warning, ArrowCircleUp } from '@phosphor-icons/react'
import { Button, Badge, LoadingSpinner, ServiceReconnectOverlay } from '../components'
import { SelectComponent as Select } from './Select'
import { HelpCard } from './HelpCard'
import { FormGroup, FormProps } from './sectioned'
import { compactAgo } from '../lib/relativeTime'
import { apiClient } from '../services'
import { useNotification } from '../contexts'
import { useServiceReconnect, UPDATE_MAX_WAIT_MS } from '../hooks'
import { MARKDOWN_ELEMENT_CLASSES } from '../lib/markdown'
import { UpdateCampaignStatus } from './UpdateCampaignStatus'

// A rolling update moves one node every minute at most: the screen follows it at this pace
const CAMPAIGN_POLL_MS = 10000

export function UpdateChecker() {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [updateInfo, setUpdateInfo] = useState(null)
  const [error, setError] = useState(null)
  const [includePrereleases, setIncludePrereleases] = useState(false)
  const [includeChannel, setIncludeChannel] = useState('stable')
  const [campaign, setCampaign] = useState(null)
  const [resuming, setResuming] = useState(false)
  const { showSuccess, showError, showConfirm } = useNotification()
  const { reconnecting, status, attempt, countdown, waitForRestart, cancel } = useServiceReconnect()

  const markdownClasses = "sf-notes-body prose prose-sm prose-invert max-w-none " + MARKDOWN_ELEMENT_CLASSES

  const checkForUpdates = async (showNotification = false, force = false) => {
    setChecking(true)
    setError(null)
    try {
      const params = `include_prereleases=${includeChannel !== 'stable'}&include_dev=${includeChannel === 'dev'}&force=${force}`
      const response = await apiClient.get(`/system/updates/check?${params}`)
      const data = response?.data || response || {}
      setUpdateInfo(data)
      setCampaign(data.update_campaign || null)
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
      t(updateInfo.ha_mode ? 'settings.installUpdateConfirmHa' : 'settings.installUpdateConfirm',
        { version: updateInfo.latest_version }),
      { title: t('settings.installUpdate'), confirmText: t('settings.installUpdate'), variant: 'primary' }
    )
    if (!confirmed) return

    setInstalling(true)
    try {
      const response = await apiClient.post('/system/updates/install', {
        include_prereleases: includeChannel !== 'stable',
        include_dev: includeChannel === 'dev'
      })
      if (updateInfo.ha_mode) {
        // HA: the nodes update one at a time, this page follows the campaign instead of a restart
        setCampaign((response?.data || response || {}).campaign || null)
        showSuccess(t('settings.updateCampaign.started', { version: updateInfo.latest_version }))
        setInstalling(false)
        return
      }
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
      t(updateInfo.ha_mode ? 'settings.majorUpgradeConfirmHa' : 'settings.majorUpgradeConfirm',
        { current: updateInfo.current_version, version: target.version }),
      { title: t('settings.majorUpgradeTitle', { version: target.version }), confirmText: t('settings.majorUpgradeInstall'), variant: 'primary' }
    )
    if (!confirmed) return

    setInstalling(true)
    try {
      const response = await apiClient.post('/system/updates/install', { major_upgrade: true, version: target.version })
      if (updateInfo.ha_mode) {
        setCampaign((response?.data || response || {}).campaign || null)
        showSuccess(t('settings.updateCampaign.started', { version: target.version }))
        setInstalling(false)
        return
      }
      showSuccess(t('settings.majorUpgradeInitiated', { version: target.version }))
      waitForRestart({ expectedVersion: target.version, maxWaitMs: UPDATE_MAX_WAIT_MS })
    } catch (err) {
      showError(err.message || t('settings.installFailed', 'Failed to install update'))
      setInstalling(false)
    }
  }

  const majorUpgrade = updateInfo?.major_upgrade || null

  const resumeCampaign = async () => {
    setResuming(true)
    try {
      const response = await apiClient.post('/system/updates/campaign/resume', {})
      setCampaign((response?.data || response || {}).campaign || null)
      showSuccess(t('settings.updateCampaign.resumed'))
    } catch (err) {
      showError(err.message || t('settings.updateCampaign.resumeFailed'))
    } finally {
      setResuming(false)
    }
  }

  const campaignRunning = campaign?.status === 'running'
  useEffect(() => {
    if (!campaignRunning) return undefined
    const timer = setInterval(async () => {
      try {
        const response = await apiClient.get('/system/updates/campaign')
        setCampaign((response?.data || response || {}).campaign || null)
      } catch {
        // the node answering may be the one restarting: the next poll reaches another
      }
    }, CAMPAIGN_POLL_MS)
    return () => clearInterval(timer)
  }, [campaignRunning])

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

  // Messages of the update check worded in the reader's language (the server sends English)
  const SERVER_MESSAGES = {
    'No releases found': 'settings.updates.noReleases',
    'No applicable releases found': 'settings.updates.noApplicable',
  }
  const serverMessage = (text) => (SERVER_MESSAGES[text] ? t(SERVER_MESSAGES[text]) : text)
  const ago = (date) => compactAgo(date, t)

  if (loading) {
    return (
      <FormGroup title={t('settings.updates.checkTitle')}>
        <p className="sf-hint" role="status">{t('settings.updates.checking')}</p>
      </FormGroup>
    )
  }

  return (
    <>
      {reconnecting && (
        <ServiceReconnectOverlay status={status} attempt={attempt} countdown={countdown} onCancel={cancel}
          note={t('reconnect.updateNote', { minutes: UPDATE_MAX_WAIT_MS / 60000 })} />
      )}
      <FormGroup
        title={updateInfo?.update_available ? t('settings.updateAvailableTitle') : t('settings.upToDateTitle')}
        badge={updateInfo?.prerelease ? <Badge variant="warning" size="sm">{t('settings.prerelease')}</Badge> : null}
        actions={(
          <>
            {updateInfo?.update_available && updateInfo?.can_auto_update && !campaignRunning && (
              <Button variant="primary" onClick={installUpdate} disabled={installing || !updateInfo.download_url}>
                {installing ? <LoadingSpinner size="xs" /> : <Download size={16} />}
                {installing ? t('settings.updates.installing') : t('settings.updates.install')}
              </Button>
            )}
            <Button variant="secondary" onClick={() => checkForUpdates(true, true)} disabled={checking}>
              <ArrowsClockwise size={16} className={checking ? 'animate-spin' : ''} />
              {checking ? t('settings.updates.checking') : t('settings.checkNow')}
            </Button>
          </>
        )}
      >
        <div className="sf-stack">
          <FormProps items={[
            [t('settings.updates.installed'), updateInfo?.current_version ? `v${updateInfo.current_version}` : '—'],
            updateInfo?.update_available && [t('settings.updates.latest'), `v${updateInfo.latest_version}`],
            updateInfo?.update_available && updateInfo?.published_at && [t('settings.updates.published'), ago(updateInfo.published_at)],
          ]} />

          {updateInfo?.ha_mode && updateInfo?.can_auto_update && (
            <p className="sf-hint">{t('settings.updateCampaign.haNote')}</p>
          )}

          {updateInfo?.update_available && !updateInfo?.can_auto_update && (
            <p className="sf-hint">
              {t('settings.updates.dockerHint')}{' '}
              <code>{`docker pull ${updateInfo.download_url || `ghcr.io/neyslim/ultimate-ca-manager:${updateInfo.latest_version}`}`}</code>
            </p>
          )}

          {error && <p className="ui-error" role="alert"><Warning aria-hidden="true" />{error}</p>}

          {updateInfo?.message && !updateInfo?.update_available && (
            <p className="sf-hint">{serverMessage(updateInfo.message)}</p>
          )}

          {/* Later major version: never installed automatically */}
          {majorUpgrade && (
            <ul className="sf-records">
              <li>
                <div className="sf-record-main">
                  <strong>{t('settings.majorUpgradeTitle', { version: majorUpgrade.version })}</strong>
                  <span className="sf-record-meta">{t('settings.majorUpgradeDesc')}</span>
                  {majorUpgrade.html_url && (
                    <a className="sf-link" href={majorUpgrade.html_url} target="_blank" rel="noopener noreferrer">
                      {t('settings.majorUpgradeNotes')}
                    </a>
                  )}
                  {!updateInfo?.can_auto_update && (
                    <span className="sf-record-meta">
                      {t('settings.majorUpgradeDocker', { image: majorUpgrade.download_url || `ghcr.io/neyslim/ultimate-ca-manager:${majorUpgrade.version}` })}
                    </span>
                  )}
                </div>
                {updateInfo?.can_auto_update && !campaignRunning && (
                  <div className="sf-record-actions">
                    <Button variant="secondary" onClick={installMajorUpgrade} disabled={installing || !majorUpgrade.download_url}>
                      <ArrowCircleUp size={16} />
                      {t('settings.majorUpgradeInstall')}
                    </Button>
                  </div>
                )}
              </li>
            </ul>
          )}

          <UpdateCampaignStatus campaign={campaign} onResume={resumeCampaign} resuming={resuming} />

          {/* Release notes of the running version, then of the available one */}
          {updateInfo?.current_release_notes && (
            <details className="sf-notes">
              <summary>
                {t('settings.currentReleaseNotes', { version: updateInfo.current_version })}
                {updateInfo.current_published_at && <span>{` (${ago(updateInfo.current_published_at)})`}</span>}
              </summary>
              <div className={markdownClasses}>
                <ReactMarkdown>{updateInfo.current_release_notes}</ReactMarkdown>
              </div>
            </details>
          )}
          {updateInfo?.update_available && updateInfo?.release_notes && (
            <details className="sf-notes" open>
              <summary>{t('settings.updateReleaseNotes', { version: updateInfo.latest_version })}</summary>
              <div className={markdownClasses}>
                <ReactMarkdown>{updateInfo.release_notes}</ReactMarkdown>
              </div>
            </details>
          )}

          {/* Versions the check looks at; the scheduled channel is set under automatic updates */}
          <div className="sf-grid">
            <Select
              label={t('settings.updates.checkChannel')}
              value={includeChannel}
              onChange={(value) => setIncludeChannel(value)}
              options={[
                { value: 'stable', label: t('settings.channelStable') },
                { value: 'prerelease', label: t('settings.channelPrerelease') },
                { value: 'dev', label: t('settings.channelDev') },
              ]}
            />
          </div>
          {includeChannel === 'dev' && <HelpCard variant="warning">{t('settings.channelDevWarning')}</HelpCard>}
          {updateInfo?.html_url && (
            <p className="sf-hint">
              <a className="sf-link" href={updateInfo.html_url} target="_blank" rel="noopener noreferrer">{t('settings.viewOnGithub')}</a>
            </p>
          )}
        </div>
      </FormGroup>
    </>
  )
}

export default UpdateChecker
