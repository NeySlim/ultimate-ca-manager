import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TestTube, FloppyDisk, Plus, Trash, CheckCircle, XCircle } from '@phosphor-icons/react'
import { Button, Input, Textarea } from '../../components'
import { formatDate } from '../../lib/utils'
import { adConnectorService } from '../../services'
import { useNotification } from '../../contexts'

// Rows need a key that survives reordering after a removal; the hostname
// itself can't serve as one while it's still being typed (it's empty, and
// two blank rows would collide).
let nextRowId = 0
const toRows = (servers) => (servers?.length ? servers : ['']).map(value => ({ id: ++nextRowId, value }))

export default function AdConnectorForm({ config, onSave, onCancel }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showWarning } = useNotification()
  const [testing, setTesting] = useState(false)
  const [testResults, setTestResults] = useState(null)
  const [rows, setRows] = useState(() => toRows(config?.servers))
  // Health comes from the scheduled probe, so it describes the saved
  // config. A row the user has just typed has no health yet, and an edited
  // one's health belongs to the old hostname -- resultFor keys on the
  // hostname, so both simply miss, which is the honest answer.
  const health = config?.health?.servers || {}
  const [formData, setFormData] = useState({
    port: config?.port || 389,
    health_probe_interval: config?.health_probe_interval || 120,
    use_ssl: config?.use_ssl ?? false,
    verify_ssl: config?.verify_ssl ?? true,
    ca_bundle: config?.ca_bundle || '',
    base_dn: config?.base_dn || '',
    bind_dn: config?.bind_dn || '',
    bind_password: '',
    enabled: config?.enabled ?? false,
  })

  const servers = rows.map(r => r.value.trim()).filter(Boolean)

  const updateField = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  // Any edit to the server list invalidates the results shown against it --
  // leaving a stale green tick next to a hostname the admin just changed
  // would be worse than showing nothing.
  const updateRow = (id, value) => {
    setRows(prev => prev.map(r => (r.id === id ? { ...r, value } : r)))
    setTestResults(null)
  }
  const removeRow = (id) => {
    setRows(prev => (prev.length > 1 ? prev.filter(r => r.id !== id) : prev))
    setTestResults(null)
  }
  const addRow = () => {
    setRows(prev => [...prev, { id: ++nextRowId, value: '' }])
    setTestResults(null)
  }

  const payload = () => ({ ...formData, servers })

  const handleSubmit = (e) => {
    e.preventDefault()
    const data = payload()
    // Don't send the masked placeholder back if the password is unchanged
    if (config?.id && !data.bind_password) delete data.bind_password
    onSave(data)
  }

  const handleTestConnection = async () => {
    if (!servers.length) return
    setTesting(true)
    setTestResults(null)
    try {
      // Always test the current (possibly unsaved) form values -- testing
      // the saved config here would silently ignore any edit the user just
      // made (e.g. a corrected bind DN) until they hit Save.
      const response = await adConnectorService.test(payload())
      setTestResults(response.data?.servers || null)
      const message = response.data?.message || t('adConnector.testSuccess')
      // A partial pass is not a pass: the connector works today only
      // because the reachable DC happens to be up.
      if (response.data?.partial) showWarning(message)
      else showSuccess(message)
    } catch (error) {
      setTestResults(error.data?.details?.servers || null)
      showError(error.message || t('adConnector.testFailed'))
    } finally {
      setTesting(false)
    }
  }

  const resultFor = (host) => testResults?.find(r => r.server === host.trim())

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <div className="space-y-2">
        <label className="block text-xs font-medium text-text-secondary leading-[20px]">
          <span className="flex items-center gap-1 h-[20px]">
            {t('adConnector.servers')}
            <span className="status-danger-text">*</span>
          </span>
        </label>
        <p className="text-xs text-text-tertiary">{t('adConnector.serversHint')}</p>
        {rows.map((row) => {
          const host = row.value.trim()
          const result = host ? resultFor(host) : null
          const probed = !result && host ? health[host] : null
          return (
            <div key={row.id}>
              <div className="grid grid-cols-[1fr_auto] gap-2 items-center">
                <Input
                  value={row.value}
                  onChange={(e) => updateRow(row.id, e.target.value)}
                  placeholder={t('adConnector.serverPlaceholder')}
                  required={!servers.length}
                />
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => removeRow(row.id)}
                  disabled={rows.length === 1}
                  aria-label={t('common.remove')}
                >
                  <Trash size={14} className="text-status-danger" />
                </Button>
              </div>
              {result && (
                <p className={`flex items-start gap-1 mt-1 text-xs ${result.success ? 'text-status-success' : 'text-status-danger'}`}>
                  {result.success
                    ? <CheckCircle size={14} weight="bold" className="shrink-0 mt-px" />
                    : <XCircle size={14} weight="bold" className="shrink-0 mt-px" />}
                  <span className="break-all">{result.message}</span>
                </p>
              )}
              {probed && (
                <p className={`flex items-start gap-1 mt-1 text-xs ${probed.healthy ? 'text-status-success' : 'text-status-danger'}`}>
                  {probed.healthy
                    ? <CheckCircle size={14} weight="bold" className="shrink-0 mt-px" />
                    : <XCircle size={14} weight="bold" className="shrink-0 mt-px" />}
                  <span className="break-all">
                    {probed.healthy
                      ? t('adConnector.healthUp')
                      : t('adConnector.healthDown', { since: formatDate(probed.since) })}
                  </span>
                </p>
              )}
            </div>
          )
        })}
        <Button type="button" size="sm" variant="secondary" onClick={addRow}>
          <Plus size={14} /> {t('adConnector.addServer')}
        </Button>
      </div>

      <Input
        label={t('adConnector.port')}
        type="number"
        value={formData.port}
        onChange={(e) => updateField('port', parseInt(e.target.value, 10) || 389)}
        required
      />

      <Input
        label={t('adConnector.probeInterval')}
        type="number"
        min={60}
        max={86400}
        value={formData.health_probe_interval}
        onChange={(e) => updateField('health_probe_interval', parseInt(e.target.value, 10) || 120)}
        helperText={t('adConnector.probeIntervalHint')}
        required
      />

      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={formData.use_ssl} onChange={(e) => updateField('use_ssl', e.target.checked)} className="rounded" />
          {t('adConnector.useSsl')}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={formData.verify_ssl} onChange={(e) => updateField('verify_ssl', e.target.checked)} className="rounded" />
          {t('adConnector.verifySsl')}
        </label>
      </div>

      {formData.verify_ssl && (
        <Textarea
          label={t('adConnector.caBundle')}
          value={formData.ca_bundle}
          onChange={(e) => updateField('ca_bundle', e.target.value)}
          rows={3}
          placeholder="-----BEGIN CERTIFICATE-----"
          className="font-mono text-xs"
        />
      )}

      <Input
        label={t('adConnector.baseDn')}
        value={formData.base_dn}
        onChange={(e) => updateField('base_dn', e.target.value)}
        placeholder={t('adConnector.baseDnPlaceholder')}
        required
      />
      {/* The switch asks for both, the same rule update_config applies. A
          blank password on a stored one means "unchanged", and handleSubmit
          drops it from the payload. */}
      <Input
        label={t('adConnector.bindDn')}
        value={formData.bind_dn}
        onChange={(e) => updateField('bind_dn', e.target.value)}
        placeholder={t('adConnector.bindDnPlaceholder')}
        required={formData.enabled}
      />
      <Input
        label={t('adConnector.bindPassword')}
        type="password"
        value={formData.bind_password}
        onChange={(e) => updateField('bind_password', e.target.value)}
        required={formData.enabled && !config?.bind_password}
        hasExistingValue={Boolean(config?.bind_password)}
      />

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={formData.enabled} onChange={(e) => updateField('enabled', e.target.checked)} className="rounded" />
        {t('common.enabled')}
      </label>

      <div className="flex justify-between gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={handleTestConnection} disabled={!servers.length || testing}>
          <TestTube size={16} />
          {testing ? t('common.testing') : t('adConnector.testConnection')}
        </Button>
        <div className="flex gap-2">
          <Button type="button" variant="secondary" onClick={onCancel}>
            {t('common.cancel')}
          </Button>
          <Button type="submit">
            <FloppyDisk size={16} />
            {t('common.save')}
          </Button>
        </div>
      </div>
    </form>
  )
}
