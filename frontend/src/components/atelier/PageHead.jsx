/**
 * The mockup's pageHead() and moduleHead(): the title (focused by script after a navigation),
 * the total in words, one sentence of intent, then the page actions, the main one last.
 */
import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'
import { IconBtn } from './Btn'
import { useDisclosure, moveFocus } from '../shell/useDisclosure'

/**
 * `more`: the head's secondary actions ({ id, icon, label, onClick, disabled }), which a phone hides from the head
 * (the mockup's rule): under 800 px they are reached from a « ⋯ » menu instead, as the journal's actions.
 * `bar`: a form's save state and buttons, held at the right of the head while the page scrolls.
 */
export function PageHead({ title, total, intent, actions, more, bar }) {
  const items = (more || []).filter(Boolean)
  return (
    <header className="page-head">
      <div>
        <div className="title-line">
          <h1 id="main-title" tabIndex={-1}>{title}</h1>
          <span className="total">{total ?? ''}</span>
        </div>
        {intent && <p>{intent}</p>}
      </div>
      {(actions || items.length > 0) && <div className="actions">{items.length > 0 && <PageMore items={items} />}{actions}</div>}
      {bar}
    </header>
  )
}

function PageMore({ items }) {
  const { t } = useTranslation()
  const { open, setOpen, close, buttonRef, rootProps } = useDisclosure()
  const menuRef = useRef(null)
  const entries = () => [...(menuRef.current?.querySelectorAll('button:not([disabled])') || [])]
  const onKeyDown = (e) => {
    rootProps.onKeyDown(e)
    if (open && !e.defaultPrevented) moveFocus(e, entries())
  }
  return (
    <div className="pop-wrap page-more" {...rootProps} onKeyDown={onKeyDown}>
      <IconBtn ref={buttonRef} quiet icon="more" data-action="page-more" label={t('common.moreActions')}
        aria-haspopup="menu" aria-expanded={open} onClick={() => { setOpen(!open); setTimeout(() => entries()[0]?.focus(), 0) }} />
      <div className="pop-menu" role="menu" ref={menuRef} hidden={!open}>
        {items.map(({ id, icon, label, onClick, disabled }) => (
          <button key={id} type="button" role="menuitem" className="pop-item" data-more={id} disabled={disabled || undefined}
            onClick={() => { close(); onClick() }}>
            {icon && <Icon name={icon} />}{label}
          </button>
        ))}
      </div>
    </div>
  )
}

export default PageHead
