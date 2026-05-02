import { useState, useEffect } from 'react'
import {
  ArrowsClockwise, Play, GearSix, CaretDown, Crosshair, Plugs
} from '@phosphor-icons/react'
import { Modal, Button, Input } from '../../components'
import TagsInput from '../../components/ui/TagsInput'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { cn } from '../../lib/utils'

export default function QuickScanModal({ open, onClose, onScan, scanning, t }) {
  const [targets, setTargets] = useState([])
  const [ports, setPorts] = useState(['443'])
  const [timeout, setTimeout_] = useState(5)
  const [maxWorkers, setMaxWorkers] = useState(20)
  const [resolveDns, setResolveDns] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)

  useEffect(() => {
    if (open) {
      setTargets([]); setPorts(['443']); setTimeout_(5)
      setMaxWorkers(20); setResolveDns(false); setShowAdvanced(false)
    }
  }, [open])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!targets.length) return
    const portList = ports.map(s => parseInt(s)).filter(n => n > 0 && n <= 65535)
    onScan({
      targets,
      ports: portList.length ? portList : [443],
      timeout,
      max_workers: maxWorkers,
      resolve_dns: resolveDns,
    })
  }

  const portPresets = [
    { label: 'HTTPS', ports: ['443'] },
    { label: 'HTTPS + Alt', ports: ['443', '8443'] },
    { label: t('discovery.allCommon'), ports: ['443', '8443', '8080', '636', '993', '995', '465', '587'] },
  ]

  const portsMatch = (a, b) => a.length === b.length && a.every((v, i) => v === b[i])

  return (
    <Modal open={open} onClose={onClose} title={t('discovery.quickScan')}>
      <form onSubmit={handleSubmit} className="p-5 space-y-5">
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
          <Button type="submit" disabled={scanning || !targets.length}>
            {scanning ? <ArrowsClockwise size={14} className="animate-spin" /> : <Play size={14} weight="fill" />}
            {t('discovery.startScan')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
