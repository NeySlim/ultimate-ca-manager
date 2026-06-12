import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { TestTube } from '@phosphor-icons/react'
import { Button, Input, Select, Textarea } from '../../components'
import CertificateInput from '../../components/CertificateInput'
import { mscaService } from '../../services'
import { useNotification } from '../../contexts'

export default function MscaConnectionForm({ connection, onSave, onCancel }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showWarning } = useNotification()
  const [testing, setTesting] = useState(false)
  const [formData, setFormData] = useState({
    name: connection?.name || '',
    server: connection?.server || '',
    ca_name: connection?.ca_name || '',
    auth_method: connection?.auth_method || 'certificate',
    username: connection?.username || '',
    password: '',
    client_cert_pem: connection?.client_cert_pem || '',
    client_key_pem: '',
    kerberos_principal: connection?.kerberos_principal || '',
    kerberos_keytab_path: connection?.kerberos_keytab_path || '',
    use_ssl: connection?.use_ssl ?? true,
    verify_ssl: connection?.verify_ssl ?? true,
    ca_bundle: connection?.ca_bundle || '',
    default_template: connection?.default_template || '',
    enabled: connection?.enabled ?? true,
  })
  const [availableTemplates, setAvailableTemplates] = useState([])
  const [fetchingTemplates, setFetchingTemplates] = useState(false)

  // Auto-fetch templates for existing connections
  useEffect(() => {
    if (connection?.id) {
      setFetchingTemplates(true)
      mscaService.getTemplates(connection.id)
        .then(res => {
          const tpls = res.data || []
          setAvailableTemplates(tpls)
          if (!formData.default_template && tpls.length > 0) {
            setFormData(prev => ({ ...prev, default_template: tpls[0] }))
          }
        })
        .catch(() => {})
        .finally(() => setFetchingTemplates(false))
    }
  }, [connection?.id])

  const updateField = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const data = { ...formData }
    // Don't send masked password if unchanged
    if (connection && !data.password) delete data.password
    if (connection && !data.client_key_pem) delete data.client_key_pem
    onSave(data)
  }

  const handleTestConnection = async () => {
    if (!formData.server) return
    setTesting(true)
    try {
      const testData = { ...formData }
      let response
      if (connection?.id) {
        response = await mscaService.test(connection.id)
      } else {
        response = await mscaService.testInline(testData)
      }
      if (response.data?.warning) {
        showWarning(t(`msca.warnings.${response.data.warning}`))
      } else {
        const tplCount = response.data?.templates?.length || 0
        showSuccess(t('msca.testSuccessWithTemplates', { count: tplCount }))
        if (response.data?.templates?.length) {
          setAvailableTemplates(response.data.templates)
        }
      }
    } catch (error) {
      showError(error.message || t('msca.testFailed'))
    } finally {
      setTesting(false)
    }
  }

  const authMethods = [
    { value: 'certificate', label: t('msca.authCertificate') },
    { value: 'kerberos', label: `${t('msca.authKerberos')} (${t('common.optional')})` },
    { value: 'basic', label: t('msca.authBasic') },
  ]

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label={`${t('msca.connectionName')} *`}
        value={formData.name}
        onChange={(e) => updateField('name', e.target.value)}
        required
      />
      <Input
        label={`${t('msca.server')} *`}
        value={formData.server}
        onChange={(e) => updateField('server', e.target.value)}
        placeholder={t('msca.serverPlaceholder')}
        required
      />
      <Input
        label={t('msca.caName')}
        value={formData.ca_name}
        onChange={(e) => updateField('ca_name', e.target.value)}
        placeholder={t('msca.caNamePlaceholder')}
      />

      <Select
        label={t('msca.authMethod')}
        options={authMethods}
        value={formData.auth_method}
        onChange={(val) => updateField('auth_method', val)}
      />

      {/* Auth-specific fields */}
      {formData.auth_method === 'basic' && (
        <>
          <Input
            label={`${t('msca.username')} *`}
            value={formData.username}
            onChange={(e) => updateField('username', e.target.value)}
          />
          <Input
            label={t('msca.password')}
            type="password"
            value={formData.password}
            onChange={(e) => updateField('password', e.target.value)}
            placeholder={connection ? '••••••••' : ''}
          />
        </>
      )}

      {formData.auth_method === 'certificate' && (
        <CertificateInput
          label={t('msca.clientCert')}
          keyLabel={t('msca.clientKey')}
          requireKey
          value={{ cert_pem: formData.client_cert_pem, key_pem: formData.client_key_pem }}
          onChange={({ cert_pem, key_pem }) => {
            updateField('client_cert_pem', cert_pem)
            updateField('client_key_pem', key_pem)
          }}
        />
      )}

      {formData.auth_method === 'kerberos' && (
        <>
          <div className="p-3 rounded-lg bg-accent-warning-op10 border border-accent-warning-op30 text-sm status-warning-text">
            {t('msca.kerberosOptionalNote')}
          </div>
          <Input
            label={t('msca.kerberosPrincipal')}
            value={formData.kerberos_principal}
            onChange={(e) => updateField('kerberos_principal', e.target.value)}
            placeholder={t('msca.kerberosPrincipalPlaceholder')}
          />
          <Input
            label={t('msca.kerberosKeytab')}
            value={formData.kerberos_keytab_path}
            onChange={(e) => updateField('kerberos_keytab_path', e.target.value)}
            placeholder={t('msca.kerberosKeytabPlaceholder')}
          />
        </>
      )}

      {availableTemplates.length > 0 ? (
        <Select
          label={t('msca.defaultTemplate')}
          options={availableTemplates.map(tpl => ({ value: tpl, label: tpl }))}
          value={formData.default_template}
          onChange={(val) => updateField('default_template', val)}
        />
      ) : (
        <div className="space-y-1">
          <Input
            label={t('msca.defaultTemplate')}
            value={formData.default_template}
            onChange={(e) => updateField('default_template', e.target.value)}
            placeholder={t('msca.defaultTemplatePlaceholder')}
          />
          {connection?.id && !fetchingTemplates && (
            <p className="text-xs text-text-tertiary">{t('msca.templatesFetchHint')}</p>
          )}
          {fetchingTemplates && (
            <p className="text-xs text-text-tertiary">{t('msca.loadingTemplates')}</p>
          )}
        </div>
      )}

      {/* SSL Settings */}
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={formData.use_ssl} onChange={(e) => updateField('use_ssl', e.target.checked)} className="rounded" />
          {t('msca.useSsl')}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={formData.verify_ssl} onChange={(e) => updateField('verify_ssl', e.target.checked)} className="rounded" />
          {t('msca.verifySsl')}
        </label>
      </div>

      {!formData.verify_ssl && (
        <Textarea
          label={t('msca.caBundle')}
          value={formData.ca_bundle}
          onChange={(e) => updateField('ca_bundle', e.target.value)}
          rows={3}
          placeholder="-----BEGIN CERTIFICATE-----"
          className="font-mono text-xs"
        />
      )}

      <div className="flex justify-between gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={handleTestConnection} disabled={!formData.server || testing}>
          <TestTube size={16} />
          {testing ? t('common.testing') : t('msca.testConnection')}
        </Button>
        <div className="flex gap-2">
          <Button type="button" variant="secondary" onClick={onCancel}>
            {t('common.cancel')}
          </Button>
          <Button type="submit">
            {connection ? t('common.save') : t('common.create')}
          </Button>
        </div>
      </div>
    </form>
  )
}
