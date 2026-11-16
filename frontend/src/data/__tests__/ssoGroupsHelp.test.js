import { describe, it, expect } from 'vitest'
import { helpContent } from '../helpContent'

const groupsItem = (title) =>
  helpContent.sso.sections.find((s) => s.title === title)
    .items.find((i) => i.label === 'Groups for role mapping').text

describe('SSO help: groups for role mapping', () => {
  // OIDC reads the roles and groups claims of the ID token and UserInfo, not SAML attributes.
  it('describes OIDC claims, not the SAML attributes', () => {
    const oidc = groupsItem('OAuth2 / OIDC')
    expect(oidc).not.toBe(groupsItem('SAML 2.0'))
    expect(oidc).toContain('ID token')
    expect(oidc).toContain('UserInfo')
    expect(oidc).toContain('about 200 groups')
    expect(oidc).not.toMatch(/groups\.link|AD FS|150 groups|attributes mapped/)
  })

  it('states the HTTPS condition of the compatibility mode', () => {
    const oidc = groupsItem('OAuth2 / OIDC')
    expect(oidc).toContain('Verify ID token signature off')
    expect(oidc).toContain('HTTPS with TLS verification on')
  })
})
