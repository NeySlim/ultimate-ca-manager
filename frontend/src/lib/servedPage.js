/**
 * The page the server sent already drawn (a guide chapter, for a valid session): React takes it
 * over as it stands, so its route renders as the server drew it until the session is checked.
 */
let served = null

/** path: the pathname the server drew, or null when the page was not taken over. */
export function setServedPage(path) {
  served = path || null
}

export const isServedPage = (pathname) => served !== null && served === pathname

/** Whether this console started from a page the server drew (kept for the page's lifetime). */
export const servedAtBoot = () => served !== null
