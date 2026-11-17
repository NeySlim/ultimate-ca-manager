/**
 * Same-origin messages between the provider screen and the sign-in test window, which is
 * opened with noopener: neither holds a reference to the other.
 */
export const CHANNEL = 'ucm-sso-sign-in-test'
export const LAUNCH_PATH = '/sso-test-launch'

export function openChannel(onMessage) {
  if (typeof BroadcastChannel === 'undefined') return null
  const channel = new BroadcastChannel(CHANNEL)
  if (onMessage) channel.onmessage = (event) => onMessage(event?.data || {})
  return channel
}

export function randomKey() {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

/** Only an http(s) URL is followed: the IdP's authorization or SSO URL. */
export function isWebUrl(value) {
  try {
    return ['http:', 'https:'].includes(new URL(value).protocol)
  } catch {
    return false
  }
}
