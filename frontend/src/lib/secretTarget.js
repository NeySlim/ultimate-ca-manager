// A saved secret only goes to the saved target: the server refuses an update
// that moves the target while keeping the secret, so forms ask for it first.
const MASKS = ['***', '********']

const norm = (value) => {
  if (value === undefined || value === null) return null
  if (typeof value === 'string') {
    const s = value.trim()
    if (!s) return null
    if (s === 'true' || s === 'false') return s === 'true'
    if (/^\d+$/.test(s)) return Number(s)
    return s
  }
  if (Array.isArray(value)) return JSON.stringify(value.map(norm))
  return value
}

export function changedTargets(saved, current, fields) {
  return fields.filter((field) => norm(saved?.[field]) !== norm(current?.[field]))
}

export function typedSecret(value) {
  return typeof value === 'string' && value.trim() !== '' && !MASKS.includes(value.trim())
}

export function secretRequiredForTarget({ saved, current, fields, secret, secretSaved }) {
  return Boolean(secretSaved) && !typedSecret(secret) && changedTargets(saved, current, fields).length > 0
}

// Props for the secret's <Input>: required, with the reason, once a target moved
export function secretInputProps(t, options) {
  if (secretRequiredForTarget(options)) {
    return { required: true, hasExistingValue: false, error: t('common.secretRequiredForTarget') }
  }
  return {}
}

const SMTP_SERVER_TARGET = ['smtp_host', 'smtp_port', 'smtp_username', 'smtp_security']
const SMTP_OAUTH_TARGET = ['smtp_oauth_tenant_id', 'smtp_oauth_client_id', 'smtp_oauth_authorize_url',
  'smtp_oauth_token_url', 'smtp_oauth_provider']

// The SMTP password and OAuth client secret, each with its own targets. Only the
// one the chosen method uses is asked for: the server drops the other on a move.
export function smtpSecretTargets(saved, current) {
  const method = current?.smtp_auth_method
  // Turning authentication off clears the username, which sends nothing anywhere
  const username = current?.smtp_auth_method === 'none' || !current?.smtp_username
    ? saved?.smtp_username : current.smtp_username
  const view = { ...current, smtp_username: username }
  return {
    password: { saved, current: view, fields: SMTP_SERVER_TARGET, secret: current?.smtp_password,
      secretSaved: method === 'password' && saved?.smtp_password === '********' },
    oauth: { saved, current: view, fields: SMTP_OAUTH_TARGET, secret: current?.smtp_oauth_client_secret,
      secretSaved: method === 'oauth2' && Boolean(saved?.has_oauth_client_secret) },
  }
}
