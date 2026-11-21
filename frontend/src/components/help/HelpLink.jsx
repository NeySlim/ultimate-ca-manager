import { Link, useInRouterContext } from 'react-router-dom'

// A guide's link to a page of the application: the router's link, a plain one outside a router
export function HelpLink({ to, children }) {
  const routed = useInRouterContext()
  return routed ? <Link className="text-link" to={to}>{children}</Link> : <a className="text-link" href={to}>{children}</a>
}
