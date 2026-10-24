import { describe, expect, it } from 'vitest'
import { buildDnsUpdateSnippets, certManagerAlgorithm, hostFromBase, isIpAddress } from '../dnsUpdateSnippets'

const build = (extra = {}) => buildDnsUpdateSnippets({
  keyName: 'actalis-1a2b3c4d.', algorithm: 'hmac-sha256', secret: 'U0VDUkVU', host: 'ucm.lan', port: 8053,
  directoryUrl: 'https://ucm.lan/acme/proxy/actalis/directory', ...extra,
})
const byId = (snippets, id) => snippets.find((s) => s.id === id)

describe('buildDnsUpdateSnippets', () => {
  it('writes a BIND key file that nsupdate -k reads', () => {
    expect(byId(build(), 'bind').code).toBe(
      'key "actalis-1a2b3c4d." {\n  algorithm hmac-sha256;\n  secret "U0VDUkVU";\n};\n')
  })

  it('names the acme.sh variables and the issue command', () => {
    const code = byId(build(), 'acmesh').code
    for (const part of ['NSUPDATE_SERVER="ucm.lan"', 'NSUPDATE_SERVER_PORT="8053"', 'NSUPDATE_KEY=', 'NSUPDATE_ZONE',
      '--dns dns_nsupdate --server https://ucm.lan/acme/proxy/actalis/directory', '--dnssleep 30']) {
      expect(code).toContain(part)
    }
  })

  it('upper-cases the certbot algorithm and never leaves the default', () => {
    for (const [alg, expected] of [['hmac-sha256', 'HMAC-SHA256'], ['hmac-sha384', 'HMAC-SHA384'], ['hmac-sha512', 'HMAC-SHA512']]) {
      expect(byId(build({ algorithm: alg }), 'certbot').code).toContain(`dns_rfc2136_algorithm = ${expected}`)
    }
  })

  it('needs an IP address for certbot: a host name becomes a placeholder', () => {
    expect(byId(build(), 'certbot').code).toContain('dns_rfc2136_server = <UCM-IP-address>')
    expect(byId(build({ host: '10.0.0.5' }), 'certbot').code).toContain('dns_rfc2136_server = 10.0.0.5')
  })

  it('sets the lego variables with the algorithm as FQDN', () => {
    const code = byId(build(), 'lego').code
    expect(code).toContain('DNSUPDATE_NAMESERVER="ucm.lan:8053"')
    expect(code).toContain('DNSUPDATE_TSIG_KEY="actalis-1a2b3c4d."')
    expect(code).toContain('DNSUPDATE_TSIG_ALGORITHM="hmac-sha256."')
  })

  it('maps the algorithm for cert-manager and refuses sha384', () => {
    expect(certManagerAlgorithm('hmac-sha256')).toBe('HMACSHA256')
    expect(certManagerAlgorithm('hmac-sha512')).toBe('HMACSHA512')
    expect(certManagerAlgorithm('hmac-sha384')).toBeNull()
    const cm = byId(build(), 'certmanager')
    for (const part of ['nameserver: ucm.lan:8053', 'tsigKeyName: actalis-1a2b3c4d.', 'tsigAlgorithm: HMACSHA256',
      'tsigSecretSecretRef:', 'tsig-secret: U0VDUkVU']) {
      expect(cm.code).toContain(part)
    }
    const cm384 = byId(build({ algorithm: 'hmac-sha384' }), 'certmanager')
    expect(cm384.code).toBeNull()
    expect(cm384.unsupported).toBe(true)
    expect(cm384.noteKeys).toContain('noteCertManagerSha384')
  })

  it('gives win-acme the enum name of the algorithm and warns about port 53', () => {
    const win = byId(build(), 'winacme')
    expect(win.code).toContain('--tsigkeyalgorithm sha256')
    expect(win.code).not.toContain('--tsigkeyalgorithm hmac-')
    // Without --validationmode dns-01, win-acme looks for an http-01 plugin named rfc2136.
    expect(win.code).toContain('--validationmode dns-01 --validation rfc2136')
    expect(win.code).not.toContain('--serverport')
    expect(win.noteKeys).toEqual(['noteWinAcmePort'])
    expect(byId(build({ algorithm: 'hmac-sha384' }), 'winacme').noteKeys).toContain('noteWinAcmeSha384')
  })

  it('passes the Posh-ACME plugin arguments and notes that the nameserver is required', () => {
    const posh = byId(build(), 'poshacme')
    for (const part of ["DDNSNameserver = 'ucm.lan'", "DDNSPort       = '8053'", "DDNSKeyType    = 'hmac-sha256'",
      'DDNSKeyValue', '-Plugin RFC2136']) {
      expect(posh.code).toContain(part)
    }
    expect(posh.noteKeys).toEqual(['notePoshNameserver'])
  })

  it('helpers: host from a URL, IP detection', () => {
    expect(hostFromBase('https://ucm.lan:8443/acme/proxy')).toBe('ucm.lan')
    expect(hostFromBase('')).toBe('ucm.example.com')
    expect(isIpAddress('10.0.0.5')).toBe(true)
    expect(isIpAddress('ucm.lan')).toBe(false)
  })
})
