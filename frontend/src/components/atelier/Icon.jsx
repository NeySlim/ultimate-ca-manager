/**
 * The mockup's icon(name): same svg element, same attributes, its path copied verbatim.
 * An unknown name draws the certificate, as the mockup does. The markup is the mockup's
 * constant paths, never data.
 */
import { PATHS } from './icons'

export function Icon({ name }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: PATHS[name] || PATHS.cert }} />
  )
}

export default Icon
