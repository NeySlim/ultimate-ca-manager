/**
 * The mockup's icon(name): same svg element, same attributes, its path copied verbatim.
 * A name the mockup lacks takes the product's own drawing in its style; an unknown name draws
 * the certificate, as the mockup does. The markup is constant paths, never data.
 */
import { PATHS } from './icons'
import { PRODUCT_PATHS } from './productIcons'

export function Icon({ name }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: PATHS[name] || PRODUCT_PATHS[name] || PATHS.cert }} />
  )
}

export default Icon
