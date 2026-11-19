import { useTranslation } from 'react-i18next'
import { ArrowDown, ArrowUp } from '@phosphor-icons/react'
import { Modal } from '../Modal'
import { PRESETS, moveCard, presetActive, presetLayout, setCardHidden } from '../../lib/overviewLayout'

/** Which cards show and in which order: presets, a checkbox and two move buttons per card. */
export function CardsDialog({ open, onClose, layout, onChange }) {
  const { t } = useTranslation()
  const title = (id) => t(`overview.cards.${id}`)
  const last = layout.order.length - 1
  return (
    <Modal open={open} onOpenChange={(next) => { if (!next) onClose() }} title={t('overview.layout.dialogTitle')} size="sm">
      <div className="ov-dialog">
        <p className="ov-dialog-note">{t('overview.layout.dialogSub')}</p>
        <div className="ov-preset-row" role="group" aria-label={t('overview.presets.label')}>
          {Object.keys(PRESETS).map((name) => (
            <button key={name} type="button" className="ov-preset" aria-pressed={presetActive(name, layout)}
              onClick={() => onChange(presetLayout(name, layout))}>
              <strong>{t(`overview.presets.${name}`)}</strong>
              <small>{name === 'all' ? t('overview.presets.allHint') : PRESETS[name].map(title).join(', ')}</small>
            </button>
          ))}
        </div>
        <ul className="ov-cards-list">
          {layout.order.map((id, i) => (
            <li key={id}>
              <label>
                <input type="checkbox" checked={!layout.hidden.includes(id)}
                  onChange={(e) => onChange(setCardHidden(layout, id, !e.target.checked))} />
                {title(id)}
              </label>
              <button type="button" className="ov-btn is-icon" disabled={i === 0}
                aria-label={t('overview.layout.up', { name: title(id) })}
                onClick={() => onChange(moveCard(layout, id, layout.order[i - 1]))}>
                <ArrowUp size={14} aria-hidden="true" />
              </button>
              <button type="button" className="ov-btn is-icon" disabled={i === last}
                aria-label={t('overview.layout.down', { name: title(id) })}
                onClick={() => onChange(moveCard(layout, id, layout.order[i + 1]))}>
                <ArrowDown size={14} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
        <p className="ov-dialog-note">{t('overview.layout.saved')}</p>
        <div className="ov-dialog-foot">
          <button type="button" className="ov-btn is-primary" onClick={onClose}>{t('common.done')}</button>
        </div>
      </div>
    </Modal>
  )
}
