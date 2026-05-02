import { useState, useEffect } from 'react'
import {
  CalendarBlank, FolderOpen, GearSix, CaretDown, Crosshair, Plugs
} from '@phosphor-icons/react'
import { Modal, Button, Input } from '../../components'
import TagsInput from '../../components/ui/TagsInput'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { cn } from '../../lib/utils'

export default function ProfileFormModal({ open, onClose, onSave, profile, t }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [targets, setTargets] = useState([])
  const [ports, setPorts] = useState(['443'])
  const [schedule, setSchedule] = useState('0')
  const [notifyEmail, setNotifyEmail] = useState('')
  const [notifyOnNew, setNotifyOnNew] = useState(true)
  const [notifyOnChange, setNotifyOnChange] = useState(true)
  const [notifyOnExpiry, setNotifyOnExpiry] = useState(true)
  const [timeout, setTimeout_] = useState(5)
  const [maxWorkers, setMaxWorkers] = useState(20)
  const [resolveDns, setResolveDns] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)

  useEffect(() => {
    if (open) {
      if (profile) {
        setName(profile.name || '')
        setDescription(profile.description || '')
        const tList = Array.isArray(profile.targets) ? profile.targets
          : (typeof profile.targets === 'string' ? (() => { try { return JSON.parse(profile.targets) } catch { return profile.targets.split(',') } })() : [])
        setTargets(tList.map(s => s.trim()).filter(Boolean))
        const pList = Array.isArray(profile.ports) ? profile.ports
          : (typeof profile.ports === 'string' ? (() => { try { return JSON.parse(profile.ports) } catch { return profile.ports.split(',') } })() : [443])
        setPorts(pList.map(String))
        setSchedule(String(profile.schedule_interval_minutes || 0))
        setNotifyEmail(profile.notify_email || '')
        setNotifyOnNew(profile.notify_on_new !== false)
        setNotifyOnChange(profile.notify_on_change !== false)
        setNotifyOnExpiry(profile.notify_on_expiry !== false)
        setTimeout_(profile.timeout || 5)
        setMaxWorkers(profile.max_workers || 20)
        setResolveDns(profile.resolve_dns || false)
        setShowAdvanced(!!(profile.resolve_dns || profile.timeout !== 5 || profile.max_workers !== 20))
      } else {
        setName(''); setDescription(''); setTargets([]); setPorts(['443'])
        setSchedule('0'); setNotifyEmail('')
        setNotifyOnNew(true); setNotifyOnChange(true); setNotifyOnExpiry(true)
        setTimeout_(5); setMaxWorkers(20); setResolveDns(false); setShowAdvanced(false)
      }
    }
  }, [open, profile])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!name.trim() || !targets.length) return
    const portList = ports.map(s => parseInt(s)).filter(n => n > 0 && n <= 65535)
    onSave({
      name: name.trim(),
      description: description.trim(),
      targets,
      ports: portList.length ? portList : [443],
      schedule_interval_minutes: parseInt(schedule) || 0,
      schedule_enabled: parseInt(schedule) > 0,
      timeout,
      max_workers: maxWorkers,
      resolve_dns: resolveDns,
      notify_email: notifyEmail.trim() || null,
      notify_on_new: notifyOnNew,
      notify_on_change: notifyOnChange,
      notify_on_expiry: notifyOnExpiry,
    })
  }

  const scheduleOptions = [
    { value: '0', label: t('discovery.manual'), icon: '—' },
    { value: '60', label: t('discovery.every1h'), icon: '1h' },
    { value: '360', label: t('discovery.every6h'), icon: '6h' },
    { value: '720', label: t('discovery.every12h'), icon: '12h' },
    { value: '1440', label: t('discovery.every24h'), icon: '24h' },
    { value: '10080', label: t('discovery.every7d'), icon: '7d' },
  ]

  const portPresets = [
    { label: 'HTTPS', ports: ['443'] },
    { label: 'HTTPS + Alt', ports: ['443', '8443'] },
    { label: t('discovery.allCommon'), ports: ['443', '8443', '8080', '636', '993', '995', '465', '587'] },
  ]

  const portsMatch = (a, b) => a.length === b.length && a.every((v, i) => v === b[i])

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={profile ? t('discovery.editProfile') : t('discovery.createProfile')}
    >
      <form onSubmit={handleSubmit} className="p-5 space-y-5 max-h-[75vh] overflow-y-auto">
        {/* ── Identity Section ── */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            <FolderOpen size={14} weight="bold" />
            {t('discovery.profile')}
          </div>
          <div className="grid grid-cols-1 gap-3">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder={t('discovery.profileNamePlaceholder')}
              label={t('common.name')}
            />
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('discovery.profileDescPlaceholder')}
              label={t('common.description')}
            />
          </div>
        </div>

        {/* ── Targets Section ── */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            <Crosshair size={14} weight="bold" />
            {t('discovery.targets')}
          </div>
          <TagsInput
            value={targets}
            onChange={setTargets}
            placeholder={t('discovery.targetsPlaceholder')}
            helperText={t('discovery.targetsTagHelp')}
          />
        </div>

        {/* ── Ports Section ── */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            <Plugs size={14} weight="bold" />
            {t('discovery.ports')}
          </div>
          <div className="flex flex-wrap gap-2">
            {portPresets.map((preset) => (
              <button
                key={preset.label}
                type="button"
                className={cn(
                  'flex flex-col items-center px-3.5 py-2 rounded-lg border text-xs transition-all',
                  portsMatch(ports, preset.ports)
                    ? 'bg-accent-op10 border-accent-primary text-accent-primary ring-1 ring-accent-primary'
                    : 'border-border bg-bg-secondary text-text-secondary hover:border-text-tertiary hover:bg-bg-tertiary'
                )}
                onClick={() => setPorts(preset.ports)}
              >
                <span className="font-medium">{preset.label}</span>
                <span className="text-2xs opacity-60 mt-0.5">{preset.ports.join(', ')}</span>
              </button>
            ))}
          </div>
          <TagsInput
            value={ports}
            onChange={setPorts}
            placeholder="443, 8443, 636"
            helperText={t('discovery.portsHelpDetailed')}
            validate={(v) => { const n = parseInt(v); return n > 0 && n <= 65535 }}
          />
        </div>

        {/* ── Schedule Section ── */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            <CalendarBlank size={14} weight="bold" />
            {t('discovery.schedule')}
          </div>
          <div className="flex flex-wrap gap-2">
            {scheduleOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={cn(
                  'px-3 py-1.5 rounded-lg border text-xs font-medium transition-all',
                  schedule === opt.value
                    ? 'bg-accent-op10 border-accent-primary text-accent-primary ring-1 ring-accent-primary'
                    : 'border-border bg-bg-secondary text-text-secondary hover:border-text-tertiary hover:bg-bg-tertiary'
                )}
                onClick={() => setSchedule(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {schedule !== '0' && (
            <div className="space-y-3">
              <Input
                label={t('discovery.notifyEmail')}
                value={notifyEmail}
                onChange={(e) => setNotifyEmail(e.target.value)}
                placeholder="admin@example.com"
                type="email"
                helperText={t('discovery.notifyEmailHelper')}
              />
              <div className="space-y-2">
                <label className="block text-xs font-medium text-text-secondary">{t('discovery.notifyEvents')}</label>
                <div className="flex flex-wrap gap-3">
                  <label className="flex items-center gap-2 text-xs cursor-pointer">
                    <input type="checkbox" checked={notifyOnNew} onChange={(e) => setNotifyOnNew(e.target.checked)} className="rounded border-border" />
                    <span className="text-text-secondary">{t('discovery.notifyOnNew')}</span>
                  </label>
                  <label className="flex items-center gap-2 text-xs cursor-pointer">
                    <input type="checkbox" checked={notifyOnChange} onChange={(e) => setNotifyOnChange(e.target.checked)} className="rounded border-border" />
                    <span className="text-text-secondary">{t('discovery.notifyOnChange')}</span>
                  </label>
                  <label className="flex items-center gap-2 text-xs cursor-pointer">
                    <input type="checkbox" checked={notifyOnExpiry} onChange={(e) => setNotifyOnExpiry(e.target.checked)} className="rounded border-border" />
                    <span className="text-text-secondary">{t('discovery.notifyOnExpiry')}</span>
                  </label>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Advanced Options ── */}
        <div className="rounded-lg border border-border overflow-hidden">
          <button
            type="button"
            className="flex items-center justify-between w-full px-4 py-2.5 text-sm text-text-secondary hover:bg-bg-secondary transition-colors"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            <span className="flex items-center gap-2">
              <GearSix size={15} weight="bold" />
              {t('discovery.advancedOptions')}
            </span>
            <CaretDown size={14} className={cn("transition-transform duration-200", showAdvanced && "rotate-180")} />
          </button>

          {showAdvanced && (
            <div className="px-4 pb-4 pt-1 space-y-4 border-t border-border bg-secondary-op50">
              <ToggleSwitch
                checked={resolveDns}
                onChange={setResolveDns}
                label={t('discovery.reverseDns')}
                description="PTR records"
                size="sm"
              />
              <div className="grid grid-cols-2 gap-3">
                <Input
                  label={t('discovery.timeout')}
                  type="number"
                  value={timeout}
                  onChange={(e) => setTimeout_(Math.min(Math.max(parseInt(e.target.value) || 1, 1), 30))}
                  min={1} max={30}
                  helperText="1–30s"
                />
                <Input
                  label={t('discovery.concurrency')}
                  type="number"
                  value={maxWorkers}
                  onChange={(e) => setMaxWorkers(Math.min(Math.max(parseInt(e.target.value) || 1, 1), 50))}
                  min={1} max={50}
                  helperText="1–50"
                />
              </div>
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={!name.trim() || !targets.length}>
            {profile ? t('common.save') : t('common.create')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
