/**
 * Security Dashboard Page
 * Displays security status, anomalies, and admin tools
 * 
 * Pro feature - shows secrets status, rotation, anomaly detection, audit integrity
 */

import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  ShieldCheck, 
  Key, 
  Warning, 
  CheckCircle, 
  XCircle,
  ArrowsClockwise,
  Eye,
  Clock,
  User,
  Globe
} from '@phosphor-icons/react'
import ResponsiveLayout from '../../components/ui/responsive/ResponsiveLayout'
import { CompactSection, CompactGrid } from '../../components/DetailCard'
import { Button } from '../../components/Button'
import { apiClient } from '../../services/apiClient'
import { useNotification } from '../../contexts/NotificationContext'
import { cn } from '../../lib/utils'

export default function SecurityDashboardPage() {
  const { t } = useTranslation()
  const { showError, showSuccess } = useNotification()
  
  const [loading, setLoading] = useState(true)
  const [secretsStatus, setSecretsStatus] = useState(null)
  const [anomalies, setAnomalies] = useState([])
  const [auditVerify, setAuditVerify] = useState(null)
  const [rotating, setRotating] = useState(false)
  const [verifying, setVerifying] = useState(false)

  // Load all security data
  useEffect(() => {
    loadSecurityData()
  }, [])

  const loadSecurityData = async () => {
    setLoading(true)
    try {
      const [secretsRes, anomaliesRes] = await Promise.all([
        apiClient.get('/system/security/secrets-status'),
        apiClient.get('/system/security/anomalies')
      ])
      
      // apiClient returns JSON directly, not axios-style response
      setSecretsStatus(secretsRes.data || secretsRes)
      setAnomalies(anomaliesRes.data?.anomalies || anomaliesRes.anomalies || [])
    } catch (error) {
      showError(t('securityDashboard.errors.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  const handleRotateSecrets = async () => {
    setRotating(true)
    try {
      const response = await apiClient.post('/system/security/rotate-secrets', {})
      const data = response.data || response
      showSuccess(t('securityDashboard.secrets.rotationSuccess'))
      
      // Show instructions in alert
      if (data.instructions) {
        alert(`${t('securityDashboard.secrets.rotationInstructions')}:\n\n${data.instructions.join('\n')}`)
      }
    } catch (error) {
      showError(error.message || t('securityDashboard.errors.rotateFailed'))
    } finally {
      setRotating(false)
    }
  }

  const handleVerifyAudit = async () => {
    setVerifying(true)
    try {
      const response = await apiClient.get('/audit/verify')
      const data = response.data || response
      setAuditVerify(data)
      
      if (data.valid) {
        showSuccess(t('securityDashboard.success.auditVerified', { count: data.checked }))
      } else {
        showError(t('securityDashboard.chainInvalid'))
      }
    } catch (error) {
      showError(error.message || t('securityDashboard.errors.verifyFailed'))
    } finally {
      setVerifying(false)
    }
  }

  // Stats for header
  const stats = [
    {
      label: t('securityDashboard.stats.secretsStatus'),
      value: secretsStatus?.jwt_secret?.configured ? t('securityDashboard.stats.configured') : t('securityDashboard.stats.notSet'),
      icon: Key,
      color: secretsStatus?.jwt_secret?.configured ? 'text-status-success' : 'text-status-danger'
    },
    {
      label: t('securityDashboard.stats.anomalies24h'),
      value: anomalies.length,
      icon: Warning,
      color: anomalies.length > 0 ? 'text-status-warning' : 'text-status-success'
    },
    {
      label: t('securityDashboard.stats.auditIntegrity'),
      value: auditVerify?.valid ? t('securityDashboard.stats.verified') : t('securityDashboard.stats.notChecked'),
      icon: ShieldCheck,
      color: auditVerify?.valid ? 'text-status-success' : 'text-text-secondary'
    }
  ]

  return (
    <ResponsiveLayout
      title={t('securityDashboard.title')}
      subtitle={t('securityDashboard.subtitle')}
      icon={ShieldCheck}
      stats={stats}
      helpPageKey="security"
      loading={loading}
    >
      <div className="space-y-6 p-4">
        {/* Secrets Status */}
        <CompactSection 
          title={t('securityDashboard.secretsStatus')} 
          icon={Key}
          iconClass="icon-bg-purple"
          defaultOpen
        >
          {secretsStatus && (
            <div className="space-y-4">
              <CompactGrid cols={3}>
                <div className="p-3 rounded-lg bg-bg-secondary">
                  <div className="flex items-center gap-2 mb-2">
                    {secretsStatus.jwt_secret?.configured ? (
                      <CheckCircle size={20} weight="fill" className="text-status-success" />
                    ) : (
                      <XCircle size={20} weight="fill" className="text-status-danger" />
                    )}
                    <span className="font-medium text-text-primary">{t('securityDashboard.secrets.jwtSecret')}</span>
                  </div>
                  <div className="text-sm text-text-secondary">
                    {secretsStatus.jwt_secret?.configured ? t('securityDashboard.secrets.configured') : t('securityDashboard.secrets.notConfigured')}
                  </div>
                  {secretsStatus.jwt_secret?.rotation_in_progress && (
                    <div className="mt-1 text-xs text-status-warning flex items-center gap-1">
                      <ArrowsClockwise size={12} className="animate-spin" />
                      {t('securityDashboard.secrets.rotationInProgress')}
                    </div>
                  )}
                </div>

                <div className="p-3 rounded-lg bg-bg-secondary">
                  <div className="flex items-center gap-2 mb-2">
                    {secretsStatus.session_secret?.configured ? (
                      <CheckCircle size={20} weight="fill" className="text-status-success" />
                    ) : (
                      <XCircle size={20} weight="fill" className="text-status-danger" />
                    )}
                    <span className="font-medium text-text-primary">{t('securityDashboard.secrets.sessionSecret')}</span>
                  </div>
                  <div className="text-sm text-text-secondary">
                    {secretsStatus.session_secret?.configured ? t('securityDashboard.secrets.configured') : t('securityDashboard.secrets.notConfigured')}
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-bg-secondary">
                  <div className="flex items-center gap-2 mb-2">
                    {secretsStatus.encryption_key?.configured ? (
                      <CheckCircle size={20} weight="fill" className="text-status-success" />
                    ) : (
                      <Warning size={20} weight="fill" className="text-status-warning" />
                    )}
                    <span className="font-medium text-text-primary">{t('securityDashboard.secrets.encryptionKey')}</span>
                  </div>
                  <div className="text-sm text-text-secondary">
                    {secretsStatus.encryption_key?.configured ? t('securityDashboard.secrets.configured') : t('securityDashboard.secrets.notSet')}
                  </div>
                </div>
              </CompactGrid>

              <div className="flex gap-2">
                <Button
                  onClick={handleRotateSecrets}
                  loading={rotating}
                  variant="secondary"
                  size="sm"
                >
                  <ArrowsClockwise size={16} />
                  {t('securityDashboard.rotateSecrets')}
                </Button>
              </div>
            </div>
          )}
        </CompactSection>

        {/* Anomaly Detection */}
        <CompactSection 
          title={t('securityDashboard.anomalyDetection')} 
          icon={Warning}
          iconClass="icon-bg-orange"
          badge={anomalies.length > 0 ? t('securityDashboard.alerts', { count: anomalies.length }) : null}
          badgeColor={anomalies.length > 0 ? 'warning' : 'success'}
          defaultOpen
        >
          {anomalies.length === 0 ? (
            <div className="flex items-center gap-3 p-4 rounded-lg bg-status-success/10">
              <CheckCircle size={24} weight="fill" className="text-status-success" />
              <div>
                <div className="font-medium text-text-primary">{t('securityDashboard.noAnomalies')}</div>
                <div className="text-sm text-text-secondary">{t('securityDashboard.noAnomaliesDescription')}</div>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {anomalies.map((anomaly, i) => (
                <div 
                  key={i}
                  className={cn(
                    'p-3 rounded-lg flex items-start gap-3',
                    anomaly.details?.severity === 'high' ? 'bg-status-danger/10' : 'bg-status-warning/10'
                  )}
                >
                  <Warning 
                    size={20} 
                    weight="fill" 
                    className={anomaly.details?.severity === 'high' ? 'text-status-danger' : 'text-status-warning'} 
                  />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-text-primary">
                      {anomaly.details?.type || t('securityDashboard.unknownAnomaly')}
                    </div>
                    <div className="text-sm text-text-secondary">
                      {anomaly.details?.message}
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-xs text-text-tertiary">
                      <span className="flex items-center gap-1">
                        <Clock size={12} />
                        {new Date(anomaly.timestamp).toLocaleString()}
                      </span>
                      {anomaly.details?.ip && (
                        <span className="flex items-center gap-1">
                          <Globe size={12} />
                          {anomaly.details.ip}
                        </span>
                      )}
                      {anomaly.details?.user_id && (
                        <span className="flex items-center gap-1">
                          <User size={12} />
                          {t('securityDashboard.userNumber', { id: anomaly.details.user_id })}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CompactSection>

        {/* Audit Integrity */}
        <CompactSection 
          title={t('securityDashboard.auditLogIntegrity')} 
          icon={Eye}
          iconClass="icon-bg-blue"
          defaultOpen
        >
          <div className="space-y-4">
            <p className="text-sm text-text-secondary">
              {t('securityDashboard.audit.description')}
            </p>

            {auditVerify && (
              <div className={cn(
                'p-4 rounded-lg flex items-center gap-3',
                auditVerify.valid ? 'bg-status-success/10' : 'bg-status-danger/10'
              )}>
                {auditVerify.valid ? (
                  <CheckCircle size={24} weight="fill" className="text-status-success" />
                ) : (
                  <XCircle size={24} weight="fill" className="text-status-danger" />
                )}
                <div>
                  <div className="font-medium text-text-primary">
                    {auditVerify.valid ? t('securityDashboard.audit.integrityVerified') : t('securityDashboard.audit.integrityFailed')}
                  </div>
                  <div className="text-sm text-text-secondary">
                    {t('securityDashboard.audit.entriesChecked', { count: auditVerify.checked })}
                    {auditVerify.errors?.length > 0 && ` - ${t('securityDashboard.audit.errorsFound', { count: auditVerify.errors.length })}`}
                  </div>
                </div>
              </div>
            )}

            <Button
              onClick={handleVerifyAudit}
              loading={verifying}
              variant="secondary"
              size="sm"
            >
              <ShieldCheck size={16} />
              {t('securityDashboard.verifyAuditIntegrity')}
            </Button>
          </div>
        </CompactSection>
      </div>
    </ResponsiveLayout>
  )
}
