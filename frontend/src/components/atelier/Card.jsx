/**
 * The mockup's card() and cardMenu(), a card of the overview: its title with a counter, one
 * sentence, its tools, the options menu (hide the card, customise the cards), then its body.
 * The menu opens on its first item; Escape or a click elsewhere closes it, Escape on its button.
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'

/** id: the card (card-<id>, the mockup's per-card rules); onHide, onCustomize: the two items of its menu. */
export function Card({ id, title, count, sub, tools, onHide, onCustomize, children }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const wrap = useRef(null)
  const button = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    wrap.current?.querySelector(`#card-hide-${id}`)?.focus()
    const away = (e) => { if (!wrap.current?.contains(e.target)) setOpen(false) }
    const key = (e) => {
      if (e.key !== 'Escape' || e.defaultPrevented || document.querySelector('dialog[open]')) return
      e.preventDefault()
      setOpen(false)
      button.current?.focus()
    }
    document.addEventListener('pointerdown', away)
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', key) }
  }, [open, id])
  const menu = onHide || onCustomize
  return (
    <section className={`panel dash-card card-${id}`} id={`card-${id}`} data-card={id} aria-labelledby={`card-${id}-title`}>
      <header className="panel-heading">
        <div>
          <h2 id={`card-${id}-title`} tabIndex={-1}>{title}{count !== undefined && <span className="counter">{count}</span>}</h2>
          {sub && <p>{sub}</p>}
        </div>
        <div className="card-tools">
          {tools}
          {menu && (
            <div ref={wrap} className="card-menu-wrap">
              <button ref={button} type="button" className="icon-btn quiet" id={`card-menu-btn-${id}`} data-card-menu={id} aria-expanded={open}
                aria-controls={`card-menu-${id}`} aria-label={t('atelier.cardOptions', { name: title })} title={t('atelier.cardOptionsTitle')}
                onClick={() => setOpen(!open)}>
                <Icon name="more" />
              </button>
              <div className="card-menu" id={`card-menu-${id}`} hidden={!open}>
                {onHide && <button type="button" id={`card-hide-${id}`} data-card-hide={id} onClick={() => { setOpen(false); onHide() }}><Icon name="hide" />{t('atelier.hideCard')}</button>}
                {onCustomize && <button type="button" data-action="dash-cards" onClick={() => { setOpen(false); onCustomize() }}><Icon name="cards" />{t('atelier.customizeCards')}</button>}
              </div>
            </div>
          )}
        </div>
      </header>
      {children}
    </section>
  )
}

export default Card
