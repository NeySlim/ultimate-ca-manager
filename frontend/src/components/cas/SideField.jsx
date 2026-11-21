import { useState } from 'react'
import { Icon } from '../atelier/Icon'

/**
 * A row of the CA side panel (`dl.props` of the mockup's caSide()): the label, then the value and,
 * after it, the action that changes it as a text link. `data-product` marks a row the mockup does not have.
 */
export function SideField({ label, children }) {
  return <><dt data-product="">{label}</dt><dd data-product="">{children}</dd></>
}

export function SideAction({ children, ...rest }) {
  return <>{' '}<button type="button" className="text-link" data-write="" {...rest}>{children}</button></>
}

/** A folded section of the side panel (the product's details beyond the mockup's sections): its title opens it. */
export function SideFold({ id, title, children, onToggle, testId }) {
  const [open, setOpen] = useState(false)
  return (
    <section className="ca-side-section ca-fold" data-testid={testId}>
      <h3 className="section-title">
        <button type="button" className="fold-toggle" id={`${id}-toggle`} aria-expanded={open} aria-controls={id}
          onClick={() => { setOpen(!open); onToggle?.(!open) }}>
          <Icon name={open ? 'down' : 'right'} />{title}
        </button>
      </h3>
      <div id={id} hidden={!open}>{open && children}</div>
    </section>
  )
}
