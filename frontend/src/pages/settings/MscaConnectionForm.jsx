import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn } from '../../components/atelier'
import { Input, NumberInput, SecretInput, Select, Textarea, ToggleSwitch, Notice } from '../../components/atelier/Form'
import CertificateInput from '../../components/CertificateInput'
import { mscaService } from '../../services'
import { useNotification } from '../../contexts'
import { secretInputProps, secretRequiredForTarget, typedSecret } from '../../lib/secretTarget'

const WINRM_TARGET = ['winrm_host', 'winrm_port', 'winrm_use_ssl', 'winrm_verify_ssl',
  'winrm_transport', 'winrm_username']

// What a connection test reads from the form; a secret not retyped stays on the server
const TESTED_FIELDS = ['server', 'ca_name', 'auth_method', 'username', 'client_cert_pem',
  'kerberos_principal', 'kerberos_keytab_path', 'use_ssl', 'verify_ssl', 'ca_bundle']

function testedValues(formData) {
  const values = Object.fromEntries(TESTED_FIELDS.map((field) => [field, formData[field]]))
  if (formData.password) values.password = formData.password
  if (formData.client_key_pem) values.client_key_pem = formData.client_key_pem
  return values
}

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
    verify_ssl: connection?.verify_ssl ?? true,
    ca_bundle: connection?.ca_bundle || '',
    default_template: connection?.default_template || '',
    enabled: connection?.enabled ?? true,
    crl_sync_enabled: connection?.crl_sync_enabled ?? false,
    crl_url: connection?.crl_url || '',
    winrm_enabled: connection?.winrm_enabled ?? false,
    winrm_host: connection?.winrm_host || '',
    winrm_port: connection?.winrm_port || 5986,
    winrm_use_ssl: connection?.winrm_use_ssl ?? true,
    winrm_verify_ssl: connection?.winrm_verify_ssl ?? true,
    winrm_transport: connection?.winrm_transport || 'kerberos',
    winrm_username: connection?.winrm_username || '',
    winrm_password: '',
    ca_config: connection?.ca_config || '',
    inventory_sync_enabled: connection?.inventory_sync_enabled ?? false,
  })
  // The form as loaded: what each saved password was saved for
  const [savedForm] = useState(formData)
  const [testingAdmin, setTestingAdmin] = useState(false)
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

  // Same rule as the server: each saved password stays with the host it is sent to
  const winrmSecret = {
    saved: savedForm, current: formData, secret: formData.winrm_password,
    secretSaved: Boolean(connection?.winrm_password),
    fields: connection?.winrm_host ? WINRM_TARGET : [...WINRM_TARGET, 'server'],
  }
  const basicSecret = {
    saved: savedForm, current: formData, secret: formData.password,
    secretSaved: Boolean(connection?.auth_method === 'basic' && connection?.password
      && formData.auth_method === 'basic'),
    fields: ['server', 'verify_ssl', 'ca_bundle', 'username',
      ...(connection?.winrm_password || typedSecret(formData.winrm_password) ? [] : WINRM_TARGET)],
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (secretRequiredForTarget(winrmSecret) || secretRequiredForTarget(basicSecret)) {
      showError(t('common.secretRequiredForTarget'))
      return
    }
    const data = { ...formData }
    // Don't send masked password if unchanged
    if (connection && !data.password) delete data.password
    if (connection && !data.client_key_pem) delete data.client_key_pem
    if (connection && !data.winrm_password) delete data.winrm_password
    onSave(data)
  }

  const handleTestAdminChannel = async () => {
    if (!connection?.id) return
    setTestingAdmin(true)
    try {
      // Send the current form values so the test matches what will be saved
      const overrides = {
        winrm_enabled: formData.winrm_enabled,
        winrm_host: formData.winrm_host,
        winrm_port: formData.winrm_port,
        winrm_use_ssl: formData.winrm_use_ssl,
        winrm_verify_ssl: formData.winrm_verify_ssl,
        winrm_transport: formData.winrm_transport,
        winrm_username: formData.winrm_username,
        ca_config: formData.ca_config,
        // A Kerberos channel signs in with these; the route needs admin:system and shows the server's refusal
        kerberos_principal: formData.kerberos_principal,
        kerberos_keytab_path: formData.kerberos_keytab_path,
      }
      if (formData.winrm_password) overrides.winrm_password = formData.winrm_password
      const res = await mscaService.testAdminChannel(connection.id, overrides)
      showSuccess(t('msca.adminChannelTestSuccess', { status: res.data?.certsvc_status || '?' }))
    } catch (error) {
      showError(error.message || t('msca.adminChannelTestFailed'))
    } finally {
      setTestingAdmin(false)
    }
  }

  const handleTestConnection = async () => {
    if (!formData.server) return
    setTesting(true)
    try {
      const testData = { ...formData }
      let response
      if (connection?.id) {
        // The saved password goes only where it was saved for (as on save)
        if (secretRequiredForTarget(basicSecret)) {
          showError(t('common.secretRequiredForTarget'))
          return
        }
        response = await mscaService.test(connection.id, testedValues(formData))
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

  // The mockup's dialog form: the connection in `.form-fields`, the CRL sync and the WinRM channel under their switches, then test and actions
  return (
    <form onSubmit={handleSubmit}>
      <div className="form-fields">
        <Input id="msca-name" label={t('msca.connectionName')} value={formData.name} onChange={(e) => updateField('name', e.target.value)} required data-autofocus="" />
        <Input id="msca-server" label={t('msca.server')} value={formData.server} onChange={(e) => updateField('server', e.target.value)}
          placeholder={t('msca.serverPlaceholder')} required />
        <Input id="msca-ca-name" label={t('msca.caName')} value={formData.ca_name} onChange={(e) => updateField('ca_name', e.target.value)}
          placeholder={t('msca.caNamePlaceholder')} />
        <Select id="msca-auth" label={t('msca.authMethod')} options={authMethods} value={formData.auth_method} onChange={(val) => updateField('auth_method', val)} />

        {/* Auth-specific fields */}
        {formData.auth_method === 'basic' && (
          <>
            <Input id="msca-username" label={t('msca.username')} value={formData.username} onChange={(e) => updateField('username', e.target.value)} />
            <SecretInput id="msca-password" label={t('msca.password')} value={formData.password} onChange={(e) => updateField('password', e.target.value)}
              placeholder={connection ? '••••••••' : ''} {...secretInputProps(t, basicSecret)} />
          </>
        )}
        {formData.auth_method === 'certificate' && (
          // The certificate picker's fields span the form's two columns
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
            <Notice tone="warn">{t('msca.kerberosOptionalNote')}</Notice>
            <Input id="msca-krb-principal" label={t('msca.kerberosPrincipal')} value={formData.kerberos_principal}
              onChange={(e) => updateField('kerberos_principal', e.target.value)} placeholder={t('msca.kerberosPrincipalPlaceholder')} />
            <Input id="msca-krb-keytab" label={t('msca.kerberosKeytab')} value={formData.kerberos_keytab_path}
              onChange={(e) => updateField('kerberos_keytab_path', e.target.value)} placeholder={t('msca.kerberosKeytabPlaceholder')} />
          </>
        )}

        {availableTemplates.length > 0 ? (
          <Select id="msca-template" label={t('msca.defaultTemplate')} options={availableTemplates.map(tpl => ({ value: tpl, label: tpl }))}
            value={formData.default_template} onChange={(val) => updateField('default_template', val)} />
        ) : (
          <Input id="msca-template" label={t('msca.defaultTemplate')} value={formData.default_template}
            onChange={(e) => updateField('default_template', e.target.value)} placeholder={t('msca.defaultTemplatePlaceholder')}
            hint={fetchingTemplates ? t('msca.loadingTemplates') : connection?.id ? t('msca.templatesFetchHint') : undefined} />
        )}

        <ToggleSwitch checked={formData.verify_ssl} onChange={(v) => updateField('verify_ssl', v)} label={t('msca.verifySsl')} />
        {formData.verify_ssl && (
          <Textarea id="msca-ca-bundle" label={t('msca.caBundle')} value={formData.ca_bundle} onChange={(e) => updateField('ca_bundle', e.target.value)}
            rows={3} placeholder="-----BEGIN CERTIFICATE-----" mono />
        )}

        {/* CRL revocation sync (one-way CA → UCM) */}
          <ToggleSwitch checked={formData.crl_sync_enabled} onChange={(v) => updateField('crl_sync_enabled', v)} label={t('msca.crlSyncEnable')}
            description={formData.crl_sync_enabled ? t('msca.crlSyncHint') : undefined} />
          {formData.crl_sync_enabled && (
            <Input id="msca-crl-url" full label={t('msca.crlUrl')} value={formData.crl_url} onChange={(e) => updateField('crl_url', e.target.value)}
              placeholder={t('msca.crlUrlPlaceholder')} />
          )}

        {/* WinRM admin channel (revoke/unrevoke/publish CRL/inventory on the CA) */}
          <ToggleSwitch checked={formData.winrm_enabled} onChange={(v) => updateField('winrm_enabled', v)} label={t('msca.winrmEnable')}
            description={formData.winrm_enabled ? t('msca.winrmHint') : undefined} />
          {formData.winrm_enabled && (
            <>
              <Input id="msca-winrm-host" label={t('msca.winrmHost')} value={formData.winrm_host} onChange={(e) => updateField('winrm_host', e.target.value)}
                placeholder={formData.server || t('msca.winrmHostPlaceholder')} />
              <NumberInput id="msca-winrm-port" label={t('msca.winrmPort')} value={formData.winrm_port} onChange={(e) => updateField('winrm_port', e.target.value)} />
              <Select id="msca-winrm-transport" label={t('msca.winrmTransport')}
                options={[
                  { value: 'kerberos', label: `Kerberos (${t('common.recommended')})` },
                  { value: 'ntlm', label: 'NTLM' },
                ]}
                value={formData.winrm_transport} onChange={(val) => updateField('winrm_transport', val)} />
              <ToggleSwitch checked={formData.winrm_use_ssl} onChange={(v) => updateField('winrm_use_ssl', v)} label={t('msca.winrmUseSsl')} />
              {formData.winrm_use_ssl && (
                <ToggleSwitch checked={formData.winrm_verify_ssl} onChange={(v) => updateField('winrm_verify_ssl', v)} label={t('msca.winrmVerifySsl')} />
              )}
              <Notice>{t('msca.winrmCredsHint')}</Notice>
              <Input id="msca-winrm-user" label={t('msca.winrmUsername')} value={formData.winrm_username} onChange={(e) => updateField('winrm_username', e.target.value)}
                placeholder={t('msca.winrmUsernamePlaceholder')} />
              <SecretInput id="msca-winrm-password" label={t('msca.winrmPassword')} value={formData.winrm_password}
                onChange={(e) => updateField('winrm_password', e.target.value)} placeholder={connection?.winrm_username ? '••••••••' : ''}
                {...secretInputProps(t, winrmSecret)} />
              <Input id="msca-ca-config" full label={t('msca.caConfig')} value={formData.ca_config} onChange={(e) => updateField('ca_config', e.target.value)}
                placeholder={t('msca.caConfigPlaceholder')} />
              {connection?.id && (
                <div className="settings-test">
                  <Btn icon="send" onClick={handleTestAdminChannel} disabled={testingAdmin || undefined}>
                    {testingAdmin ? t('common.testing') : t('msca.testAdminChannel')}
                  </Btn>
                </div>
              )}
              <ToggleSwitch checked={formData.inventory_sync_enabled} onChange={(v) => updateField('inventory_sync_enabled', v)}
                label={t('msca.inventorySyncEnable')} description={formData.inventory_sync_enabled ? t('msca.inventorySyncHint') : undefined} />
            </>
          )}

        <div className="settings-test">
          <Btn icon="send" onClick={handleTestConnection} disabled={!formData.server || testing || undefined}>
            {testing ? t('common.testing') : t('msca.testConnection')}
          </Btn>
        </div>
      </div>

      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        <Btn type="submit" tone="primary" icon="check">{connection ? t('common.save') : t('common.create')}</Btn>
      </div>
    </form>
  )
}
