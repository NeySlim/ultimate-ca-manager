/**
 * The mockup's cardsDialog() and cardsBody(): the presets, then every card in the order of the
 * page with its checkbox and two move buttons; a change applies at once.
 */
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Btn, IconBtn } from '../atelier'
import { PRESETS, moveCard, presetActive, presetLayout, setCardHidden } from '../../lib/overviewLayout'

/** returnTo: where the focus goes on closing when the opener is gone (a card's menu button, else Cards). */
export function CardsDialog({ onClose, layout, onChange, returnTo = 'dash-cards-button' }) {
  const { t } = useTranslation()
  const title = (id) => t(`overview.cards.${id}`)
  const last = layout.order.length - 1
  // A move keeps the focus on its button, or on the other one when it reached the end
  const move = (id, target, focusId, fallback) => {
    onChange(moveCard(layout, id, target))
    requestAnimationFrame(() => {
      let el = document.getElementById(focusId)
      if (el?.disabled) el = document.getElementById(fallback)
      el?.focus()
    })
  }
  return (
    <AtelierDialog title={t('overview.layout.dialogTitle')} subtitle={t('overview.layout.dialogSub')} size="narrow"
      onClose={onClose} returnTo={returnTo} testId="cards-dialog">
      <div id="cards-dialog">
        <div className="preset-row" role="group" aria-label={t('overview.presets.rowLabel')}>
          {Object.keys(PRESETS).map((name) => (
            <button key={name} type="button" className="preset-btn" id={`preset-${name}`} data-dash-preset={name}
              aria-pressed={presetActive(name, layout)} onClick={() => onChange(presetLayout(name, layout))}>
              <strong>{t(`overview.presets.${name}`)}</strong>
              <small>{name === 'all' ? t('overview.presets.allHint') : PRESETS[name].map(title).join(', ')}</small>
            </button>
          ))}
        </div>
        <ol className="cards-list" aria-label={t('overview.layout.listLabel')}>
          {layout.order.map((id, i) => (
            <li key={id}>
              <label className="checkbox-line">
                <input type="checkbox" id={`card-toggle-${id}`} data-card-toggle={id} checked={!layout.hidden.includes(id)}
                  onChange={(e) => onChange(setCardHidden(layout, id, !e.target.checked))} />
                {title(id)}
              </label>
              <IconBtn icon="up" id={`card-up-${id}`} data-card-move={id} data-dir="-1" title={false}
                label={t('overview.layout.up', { name: title(id) })} disabled={i === 0}
                onClick={() => move(id, layout.order[i - 1], `card-up-${id}`, `card-down-${id}`)} />
              <IconBtn icon="down" id={`card-down-${id}`} data-card-move={id} data-dir="1" title={false}
                label={t('overview.layout.down', { name: title(id) })} disabled={i === last}
                onClick={() => move(id, layout.order[i + 1], `card-down-${id}`, `card-up-${id}`)} />
            </li>
          ))}
        </ol>
      </div>
      <p className="small muted" style={{ marginTop: 14 }}>{t('overview.layout.saved')}</p>
      <div className="modal-actions">
        <Btn tone="primary" write={false} data-action="close-modal" onClick={onClose}>{t('common.done')}</Btn>
      </div>
    </AtelierDialog>
  )
}
