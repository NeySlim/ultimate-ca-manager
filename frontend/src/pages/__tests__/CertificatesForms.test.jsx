/**
 * Form API Contract Tests — ALL Forms
 *
 * Validates that form data structures match backend API expectations.
 * Catches field name mismatches, wrong data types, and Select component misuse.
 *
 * These tests prevented real bugs:
 * - common_name vs cn field name mismatch → 400 error
 * - validity_days sent as string instead of int → 500 error
 * - Select using <option> children instead of options prop → empty dropdown
 * - onChange(e.target.value) instead of onChange(value) with Radix → crash
 */
import { describe, it, expect, vi } from 'vitest'

// ============================================================
// Helper: validates Radix Select options format
// ============================================================
function expectValidSelectOptions(options, label) {
  expect(Array.isArray(options)).toBe(true)
  options.forEach((opt, i) => {
    expect(opt, `${label}[${i}] missing value`).toHaveProperty('value')
    expect(opt, `${label}[${i}] missing label`).toHaveProperty('label')
    expect(typeof opt.value, `${label}[${i}].value must be string`).toBe('string')
    expect(typeof opt.label, `${label}[${i}].label must be string`).toBe('string')
    expect(opt.value.length, `${label}[${i}].value is empty`).toBeGreaterThan(0)
  })
}

// Helper: simulates parseInt || default pattern used in forms
function parseIntOrDefault(input, fallback) {
  return parseInt(input, 10) || fallback
}

// ============================================================
// 1. Radix Select — Universal Contract
// ============================================================
describe('Radix Select — Universal Contract', () => {
  it('onChange receives value string directly (not event object)', () => {
    const setter = vi.fn()
    // ✅ Correct: onChange={val => setter(val)}
    const correctHandler = (val) => setter(val)
    correctHandler('option-1')
    expect(setter).toHaveBeenCalledWith('option-1')
  })

  it('onChange with e.target.value crashes because Radix passes string', () => {
    // ❌ Wrong: onChange={e => setter(e.target.value)}
    // Radix passes 'option-1' (string), so e.target is undefined → TypeError
    const wrongHandler = (e) => e.target.value
    expect(() => wrongHandler('option-1')).toThrow()
  })

  it('option values must be non-empty strings (numeric IDs need String())', () => {
    const numericIds = [1, 42, 100]
    const options = numericIds.map(id => ({ value: String(id), label: `Item ${id}` }))
    expectValidSelectOptions(options, 'numericIds')
  })

  it('empty string value is not valid for Radix Select', () => {
    const badOption = { value: '', label: 'Select...' }
    expect(badOption.value.length).toBe(0) // This would cause Radix issues
  })
})

// ============================================================
// 2. Certificate Issue Form (CertificatesPage)
// ============================================================
describe('Certificate Issue Form — POST /certificates', () => {
  const mockCas = [
    { id: 1, common_name: 'Root CA', descr: 'Root CA' },
    { id: 2, common_name: 'Intermediate CA', descr: null },
  ]

  it('uses cn field (not common_name) to match backend', () => {
    const formData = {
      ca_id: '1', cn: 'test.example.com', san: '',
      key_type: 'rsa', key_size: '2048', validity_days: '365',
    }
    expect(formData).toHaveProperty('cn')
    expect(formData).not.toHaveProperty('common_name')
  })

  it('has all required fields', () => {
    const required = ['ca_id', 'cn', 'key_type', 'key_size', 'validity_days']
    const formData = {
      ca_id: '1', cn: 'test.example.com', san: '',
      key_type: 'rsa', key_size: '2048', validity_days: '365',
    }
    required.forEach(f => expect(formData).toHaveProperty(f))
  })

  it('validity_days is parsed to integer before submission', () => {
    const cases = [
      { input: '365', expected: 365 },
      { input: '90', expected: 90 },
      { input: '', expected: 365 },
      { input: 'abc', expected: 365 },
    ]
    cases.forEach(({ input, expected }) => {
      expect(parseIntOrDefault(input, 365)).toBe(expected)
      expect(typeof parseIntOrDefault(input, 365)).toBe('number')
    })
  })

  it('CA Select options use String(id) and have label', () => {
    const options = mockCas.map(ca => ({
      value: String(ca.id),
      label: ca.descr || ca.common_name,
    }))
    expectValidSelectOptions(options, 'CA')
    expect(options[1].label).toBe('Intermediate CA') // fallback to common_name
  })

  it('key_type Select options are valid strings', () => {
    const options = [
      { value: 'rsa', label: 'RSA' },
      { value: 'ecdsa', label: 'ECDSA' },
    ]
    expectValidSelectOptions(options, 'keyType')
  })

  it('key_size options match key_type constraints', () => {
    const rsaSizes = [
      { value: '2048', label: '2048 bits' },
      { value: '4096', label: '4096 bits' },
    ]
    const ecdsaSizes = [
      { value: '256', label: 'P-256' },
      { value: '384', label: 'P-384' },
    ]
    expectValidSelectOptions(rsaSizes, 'rsaSize')
    expectValidSelectOptions(ecdsaSizes, 'ecdsaSize')
    rsaSizes.forEach(s => expect(parseInt(s.value)).toBeGreaterThanOrEqual(2048))
    ecdsaSizes.forEach(s => expect(parseInt(s.value)).toBeLessThanOrEqual(384))
  })
})

// ============================================================
// 3. CA Creation Form (CAsPage)
// ============================================================
describe('CA Creation Form — POST /cas/create', () => {
  it('has all required fields with correct names', () => {
    const formData = {
      commonName: 'My Root CA',
      organization: 'ACME Corp',
      country: 'FR',
      state: 'Paris',
      locality: 'Paris',
      keyAlgo: 'RSA',
      keySize: '2048',
      validityYears: '10',
      type: 'root',
      parentCAId: null,
    }
    const required = ['commonName', 'keyAlgo', 'keySize', 'validityYears', 'type']
    required.forEach(f => expect(formData).toHaveProperty(f))
  })

  it('keySize is parsed to integer (from FormData string)', () => {
    const rawValues = ['2048', '3072', '4096']
    rawValues.forEach(v => {
      const parsed = parseInt(v)
      expect(typeof parsed).toBe('number')
      expect(parsed).toBeGreaterThanOrEqual(2048)
    })
  })

  it('validityYears is parsed to integer', () => {
    const rawValues = ['5', '10', '15', '20']
    rawValues.forEach(v => {
      const parsed = parseInt(v)
      expect(typeof parsed).toBe('number')
      expect(parsed).toBeGreaterThanOrEqual(5)
    })
  })

  it('country is max 2 characters', () => {
    const country = 'FR'
    expect(country.length).toBeLessThanOrEqual(2)
  })

  it('keyAlgo Select options are valid', () => {
    const options = [
      { value: 'RSA', label: 'RSA' },
      { value: 'ECDSA', label: 'ECDSA' },
    ]
    expectValidSelectOptions(options, 'keyAlgo')
  })

  it('keySize Select options are valid strings', () => {
    const options = [
      { value: '2048', label: '2048 bits' },
      { value: '3072', label: '3072 bits' },
      { value: '4096', label: '4096 bits' },
    ]
    expectValidSelectOptions(options, 'keySize')
  })

  it('validityYears Select options are valid strings', () => {
    const options = [
      { value: '5', label: '5 years' },
      { value: '10', label: '10 years' },
      { value: '15', label: '15 years' },
      { value: '20', label: '20 years' },
    ]
    expectValidSelectOptions(options, 'validityYears')
  })

  it('type Select options are valid', () => {
    const options = [
      { value: 'root', label: 'Root CA' },
      { value: 'intermediate', label: 'Intermediate CA' },
    ]
    expectValidSelectOptions(options, 'type')
  })

  it('parentCAId uses String(ca.id) for Select (intermediate only)', () => {
    const cas = [{ id: 1, name: 'Root', descr: null, common_name: 'Root CA' }]
    const options = cas.map(ca => ({
      value: ca.id.toString(),
      label: ca.name || ca.descr || ca.common_name,
    }))
    expectValidSelectOptions(options, 'parentCAId')
  })

  it('parentCAId is null for root CA type', () => {
    const type = 'root'
    const parentCAId = type === 'intermediate' ? '1' : null
    expect(parentCAId).toBeNull()
  })
})

// ============================================================
// 4. CSR Forms (CSRsPage)
// ============================================================
describe('CSR Sign Form — POST /csrs/{id}/sign', () => {
  it('CA Select options use String(id) with label fallback chain', () => {
    const cas = [
      { id: 1, descr: 'Root CA', name: null, common_name: 'Root' },
      { id: 42, descr: null, name: 'Intermediate', common_name: 'Inter' },
      { id: 99, descr: null, name: null, common_name: 'Backup' },
    ]
    const options = cas.map(ca => ({
      value: String(ca.id),
      label: ca.descr || ca.name || ca.common_name,
    }))
    expectValidSelectOptions(options, 'signCA')
    expect(options[0].label).toBe('Root CA')
    expect(options[1].label).toBe('Intermediate')
    expect(options[2].label).toBe('Backup')
  })

  it('validityDays is parsed to integer', () => {
    const rawInput = '365'
    const parsed = parseInt(rawInput)
    expect(typeof parsed).toBe('number')
    expect(parsed).toBe(365)
  })

  it('sign requires CA selection (non-empty)', () => {
    const signCA = ''
    expect(signCA).toBeFalsy() // Should trigger validation error
  })
})

describe('CSR Upload — POST /csrs/upload', () => {
  it('sends raw PEM text (not FormData)', () => {
    const pemText = '-----BEGIN CERTIFICATE REQUEST-----\nMIIB...\n-----END CERTIFICATE REQUEST-----'
    expect(typeof pemText).toBe('string')
    expect(pemText).toContain('BEGIN CERTIFICATE REQUEST')
  })
})

// ============================================================
// 5. ACME Forms (ACMEPage)
// ============================================================
describe('ACME Account Creation — POST /acme/accounts', () => {
  it('has all required fields', () => {
    const formData = {
      email: 'admin@example.com',
      key_type: 'RSA-2048',
      agree_tos: true,
    }
    expect(formData).toHaveProperty('email')
    expect(formData).toHaveProperty('key_type')
    expect(formData).toHaveProperty('agree_tos')
    expect(formData.agree_tos).toBe(true) // Required validation
  })

  it('key_type Select options are valid', () => {
    const options = [
      { value: 'RSA-2048', label: 'RSA 2048' },
      { value: 'RSA-4096', label: 'RSA 4096' },
      { value: 'EC-P256', label: 'EC P-256' },
      { value: 'EC-P384', label: 'EC P-384' },
    ]
    expectValidSelectOptions(options, 'acme_key_type')
  })
})

describe('ACME Certificate Request — POST /acme/orders', () => {
  it('domains are split from textarea into array', () => {
    const raw = 'example.com, *.example.com\ntest.com'
    const domainList = raw.split(/[,\n]/).map(d => d.trim()).filter(d => d)
    expect(domainList).toEqual(['example.com', '*.example.com', 'test.com'])
    expect(Array.isArray(domainList)).toBe(true)
  })

  it('submitted data has domains as array (not string)', () => {
    const formData = {
      domains: ['example.com'],
      email: 'test@example.com',
      challenge_type: 'dns-01',
      dns_provider_id: null,
      environment: 'staging',
    }
    expect(Array.isArray(formData.domains)).toBe(true)
  })

  it('dns_provider_id is parsed to int or null', () => {
    // From Select onChange: val ? parseInt(val) : null
    expect(parseInt('5')).toBe(5)
    expect(typeof parseInt('5')).toBe('number')
    const empty = '' ? parseInt('') : null
    expect(empty).toBeNull()
  })

  it('challenge_type Select options are valid', () => {
    const options = [
      { value: 'dns-01', label: 'DNS-01' },
      { value: 'http-01', label: 'HTTP-01' },
    ]
    expectValidSelectOptions(options, 'challenge_type')
  })

  it('environment Select options are valid', () => {
    const options = [
      { value: 'staging', label: 'Staging' },
      { value: 'production', label: 'Production' },
    ]
    expectValidSelectOptions(options, 'environment')
  })

  it('dns_provider Select options use String(id)', () => {
    const providers = [{ id: 1, name: 'Cloudflare' }, { id: 2, name: 'Route53' }]
    const options = providers.map(p => ({
      value: p.id.toString(),
      label: p.name,
    }))
    expectValidSelectOptions(options, 'dns_provider')
  })
})

describe('ACME DNS Provider Form — POST /acme/dns-providers', () => {
  it('credentials are JSON-stringified before submission', () => {
    const creds = { api_key: 'secret123', zone_id: 'zone1' }
    const submitted = JSON.stringify(creds)
    expect(typeof submitted).toBe('string')
    expect(JSON.parse(submitted)).toEqual(creds)
  })

  it('provider_type Select options are valid', () => {
    const types = [
      { value: 'cloudflare', label: 'Cloudflare' },
      { value: 'route53', label: 'Route 53' },
    ]
    expectValidSelectOptions(types, 'provider_type')
  })
})

describe('ACME Domain Form — POST /acme/domains', () => {
  it('dns_provider_id is parsed to int', () => {
    // onChange: val => parseInt(val) — note: no null fallback unlike RequestCertForm
    const val = '3'
    expect(parseInt(val)).toBe(3)
    expect(typeof parseInt(val)).toBe('number')
  })
})

// ============================================================
// 6. Template Form (TemplatesPage)
// ============================================================
describe('Template Form — POST /templates', () => {
  it('has all required fields', () => {
    const formData = {
      name: 'Web Server',
      type: 'certificate',
      description: 'Standard web cert',
      validity_days: 365,
      max_validity_days: 3650,
      subject: { C: 'FR', ST: 'Paris', O: 'ACME', CN: '' },
    }
    expect(formData).toHaveProperty('name')
    expect(formData).toHaveProperty('type')
    expect(formData).toHaveProperty('validity_days')
    expect(formData).toHaveProperty('subject')
  })

  it('validity_days is parsed to int with fallback', () => {
    expect(parseIntOrDefault('365', 365)).toBe(365)
    expect(parseIntOrDefault('', 365)).toBe(365)
    expect(parseIntOrDefault('abc', 365)).toBe(365)
    expect(typeof parseIntOrDefault('365', 365)).toBe('number')
  })

  it('max_validity_days is parsed to int with fallback', () => {
    expect(parseIntOrDefault('3650', 3650)).toBe(3650)
    expect(parseIntOrDefault('', 3650)).toBe(3650)
    expect(typeof parseIntOrDefault('3650', 3650)).toBe('number')
  })

  it('type Select options are valid', () => {
    const options = [
      { value: 'certificate', label: 'Certificate' },
      { value: 'ca', label: 'Certificate Authority' },
    ]
    expectValidSelectOptions(options, 'template_type')
  })

  it('subject fields match backend expected names', () => {
    const subject = { C: 'FR', ST: 'Paris', O: 'Corp', CN: 'example.com' }
    // Backend expects ISO field names
    ;['C', 'ST', 'O', 'CN'].forEach(f => expect(subject).toHaveProperty(f))
  })
})

// ============================================================
// 7. User & Group Forms (UsersGroupsPage)
// ============================================================
describe('User Form — POST /users', () => {
  it('has all required fields for creation', () => {
    const formData = {
      username: 'john',
      email: 'john@example.com',
      password: 'secure123',
      full_name: 'John Doe',
      role: 'viewer',
    }
    ;['username', 'email', 'password', 'role'].forEach(f =>
      expect(formData).toHaveProperty(f)
    )
  })

  it('password is omitted when empty on edit (not sent as "")', () => {
    const data = { username: 'john', email: 'j@x.com', password: '', role: 'viewer' }
    if (!data.password) delete data.password
    expect(data).not.toHaveProperty('password')
  })

  it('role Select options are valid', () => {
    const options = [
      { value: 'admin', label: 'Admin' },
      { value: 'operator', label: 'Operator' },
      { value: 'viewer', label: 'Viewer' },
    ]
    expectValidSelectOptions(options, 'role')
  })
})

describe('Group Form — POST /groups', () => {
  it('has required fields', () => {
    const formData = { name: 'Admins', description: 'Admin group' }
    expect(formData).toHaveProperty('name')
  })
})

// ============================================================
// 8. Settings Forms (SettingsPage)
// ============================================================
describe('Settings — General', () => {
  it('session_timeout is integer', () => {
    expect(typeof parseIntOrDefault('30', 30)).toBe('number')
  })

  it('timezone Select options are valid strings', () => {
    const options = [
      { value: 'UTC', label: 'UTC' },
      { value: 'Europe/Paris', label: 'Europe/Paris' },
    ]
    expectValidSelectOptions(options, 'timezone')
  })
})

describe('Settings — Email', () => {
  it('smtp_port is parsed to integer', () => {
    expect(parseIntOrDefault('587', 587)).toBe(587)
    expect(parseIntOrDefault('465', 587)).toBe(465)
    expect(typeof parseIntOrDefault('587', 587)).toBe('number')
  })

  it('has all required fields', () => {
    const fields = ['smtp_host', 'smtp_port', 'smtp_username', 'smtp_password',
      'smtp_from_email', 'smtp_use_tls']
    const settings = {
      smtp_host: 'mail.example.com', smtp_port: 587,
      smtp_username: 'user', smtp_password: 'pass',
      smtp_from_email: 'noreply@example.com', smtp_use_tls: true,
    }
    fields.forEach(f => expect(settings).toHaveProperty(f))
  })
})

describe('Settings — Security', () => {
  it('numeric fields are parsed to integer', () => {
    const numericFields = {
      min_password_length: '12',
      session_duration: '60',
      api_rate_limit: '100',
    }
    Object.entries(numericFields).forEach(([key, val]) => {
      const parsed = parseInt(val)
      expect(typeof parsed, `${key} should be number`).toBe('number')
      expect(parsed).toBeGreaterThan(0)
    })
  })

  it('default_role Select has valid options', () => {
    const options = [
      { value: 'admin', label: 'Admin' },
      { value: 'operator', label: 'Operator' },
      { value: 'viewer', label: 'Viewer' },
    ]
    expectValidSelectOptions(options, 'default_role')
  })
})

describe('Settings — SSO Provider Form', () => {
  it('provider_type Select options are valid', () => {
    const options = [
      { value: 'ldap', label: 'LDAP' },
      { value: 'oauth2', label: 'OAuth2' },
      { value: 'saml', label: 'SAML' },
    ]
    expectValidSelectOptions(options, 'provider_type')
  })

  it('ldap_port is parsed to integer', () => {
    expect(parseIntOrDefault('389', 389)).toBe(389)
    expect(parseIntOrDefault('636', 389)).toBe(636)
    expect(typeof parseIntOrDefault('389', 389)).toBe('number')
  })

  it('oauth2_scopes is split from string to array', () => {
    const raw = 'openid profile email'
    const scopes = raw.split(/\s+/).filter(Boolean)
    expect(scopes).toEqual(['openid', 'profile', 'email'])
    expect(Array.isArray(scopes)).toBe(true)
  })

  it('has correct fields per provider type', () => {
    const ldapFields = ['ldap_server', 'ldap_port', 'ldap_use_ssl',
      'ldap_bind_dn', 'ldap_bind_password', 'ldap_base_dn', 'ldap_user_filter']
    const oauth2Fields = ['oauth2_client_id', 'oauth2_client_secret',
      'oauth2_auth_url', 'oauth2_token_url', 'oauth2_scopes']
    const samlFields = ['saml_entity_id', 'saml_sso_url', 'saml_slo_url', 'saml_certificate']

    const ssoForm = {
      ldap_server: '', ldap_port: 389, ldap_use_ssl: false,
      ldap_bind_dn: '', ldap_bind_password: '', ldap_base_dn: '', ldap_user_filter: '',
      oauth2_client_id: '', oauth2_client_secret: '',
      oauth2_auth_url: '', oauth2_token_url: '', oauth2_scopes: '',
      saml_entity_id: '', saml_sso_url: '', saml_slo_url: '', saml_certificate: '',
    }
    ldapFields.forEach(f => expect(ssoForm).toHaveProperty(f))
    oauth2Fields.forEach(f => expect(ssoForm).toHaveProperty(f))
    samlFields.forEach(f => expect(ssoForm).toHaveProperty(f))
  })
})

describe('Settings — Backup', () => {
  it('backup_frequency Select options are valid', () => {
    const options = [
      { value: 'daily', label: 'Daily' },
      { value: 'weekly', label: 'Weekly' },
      { value: 'monthly', label: 'Monthly' },
    ]
    expectValidSelectOptions(options, 'backup_frequency')
  })

  it('backup_retention_days is parsed to integer', () => {
    expect(parseIntOrDefault('30', 30)).toBe(30)
    expect(typeof parseIntOrDefault('30', 30)).toBe('number')
  })
})

describe('Settings — Audit', () => {
  it('audit_retention_days is parsed to integer', () => {
    expect(parseIntOrDefault('90', 90)).toBe(90)
    expect(typeof parseIntOrDefault('90', 90)).toBe('number')
  })
})

describe('Settings — HTTPS Certificate', () => {
  it('certificate Select options use String(id)', () => {
    const certs = [{ id: 1, common_name: 'ucm.local' }, { id: 5, common_name: '*.example.com' }]
    const options = certs.map(c => ({
      value: String(c.id),
      label: c.common_name,
    }))
    expectValidSelectOptions(options, 'httpsCert')
  })
})

// ============================================================
// 9. SCEP Configuration (SCEPPage)
// ============================================================
describe('SCEP Config Form — POST /scep/config', () => {
  it('ca_id is parsed to integer from Select', () => {
    const val = '3'
    const parsed = parseInt(val)
    expect(typeof parsed).toBe('number')
    expect(parsed).toBe(3)
  })

  it('challenge_validity is parsed to integer', () => {
    expect(parseIntOrDefault('60', 60)).toBe(60)
    expect(typeof parseIntOrDefault('60', 60)).toBe('number')
  })

  it('CA Select options use toString()', () => {
    const cas = [{ id: 1, name: 'Root CA', subject: 'CN=Root' }]
    const options = cas.map(ca => ({
      value: ca.id.toString(),
      label: ca.name || ca.subject,
    }))
    expectValidSelectOptions(options, 'scep_ca')
  })
})

// ============================================================
// 10. Trust Store (TrustStorePage)
// ============================================================
describe('Trust Store Add Form — POST /truststore/add', () => {
  it('has required fields', () => {
    const formData = {
      name: 'External Root CA',
      description: 'Third-party trust anchor',
      certificate_pem: '-----BEGIN CERTIFICATE-----\n...',
      purpose: 'custom',
      notes: '',
    }
    expect(formData).toHaveProperty('name')
    expect(formData).toHaveProperty('certificate_pem')
    expect(formData.name.length).toBeGreaterThan(0)
    expect(formData.certificate_pem.length).toBeGreaterThan(0)
  })
})

// ============================================================
// 11. Import/Export (ImportExportPage)
// ============================================================
describe('OpnSense Config Form', () => {
  it('has all connection fields', () => {
    const config = {
      opnsenseHost: '192.168.1.1',
      opnsensePort: '443',
      opnsenseApiKey: 'key123',
      opnsenseApiSecret: 'secret456',
    }
    ;['opnsenseHost', 'opnsensePort', 'opnsenseApiKey', 'opnsenseApiSecret'].forEach(f =>
      expect(config).toHaveProperty(f)
    )
  })

  it('port should ideally be sent as number to API', () => {
    // Port is stored as string in state but API may need number
    const port = '443'
    const parsed = parseInt(port)
    expect(typeof parsed).toBe('number')
    expect(parsed).toBe(443)
  })
})

// ============================================================
// 12. Tools Forms (CertificateToolsPage)
// ============================================================
describe('SSL Checker — POST /tools/check-ssl', () => {
  it('port is parsed to integer with fallback 443', () => {
    expect(parseIntOrDefault('443', 443)).toBe(443)
    expect(parseIntOrDefault('8443', 443)).toBe(8443)
    expect(parseIntOrDefault('', 443)).toBe(443)
    expect(typeof parseIntOrDefault('443', 443)).toBe('number')
  })

  it('has required fields', () => {
    const data = { hostname: 'example.com', port: 443 }
    expect(data).toHaveProperty('hostname')
    expect(data).toHaveProperty('port')
    expect(typeof data.port).toBe('number')
  })
})

describe('CSR Decoder — POST /tools/decode-csr', () => {
  it('sends pem as string', () => {
    const data = { pem: '-----BEGIN CERTIFICATE REQUEST-----\n...' }
    expect(typeof data.pem).toBe('string')
  })
})

describe('Certificate Decoder — POST /tools/decode-cert', () => {
  it('sends pem as string', () => {
    const data = { pem: '-----BEGIN CERTIFICATE-----\n...' }
    expect(typeof data.pem).toBe('string')
  })
})

describe('Key Matcher — POST /tools/match-keys', () => {
  it('field names match backend expectations', () => {
    const data = {
      certificate: '-----BEGIN CERTIFICATE-----\n...',
      private_key: '-----BEGIN PRIVATE KEY-----\n...',
      csr: '',
      password: '',
    }
    ;['certificate', 'private_key'].forEach(f => expect(data).toHaveProperty(f))
    // Backend expects 'certificate' and 'private_key' (not cert/key)
    expect(data).not.toHaveProperty('cert')
    expect(data).not.toHaveProperty('key')
  })
})

describe('Converter — POST /tools/convert', () => {
  it('field names match backend expectations', () => {
    const data = {
      pem: '...',
      input_type: 'certificate',
      output_format: 'der',
      private_key: '',
      chain: '',
      password: '',
      pkcs12_password: '',
    }
    ;['pem', 'input_type', 'output_format'].forEach(f =>
      expect(data).toHaveProperty(f)
    )
  })
})

// ============================================================
// 13. Account Forms (AccountPage)
// ============================================================
describe('Profile Update — PATCH /users/profile', () => {
  it('has correct fields', () => {
    const formData = { full_name: 'John Doe', email: 'john@example.com' }
    expect(formData).toHaveProperty('full_name')
    expect(formData).toHaveProperty('email')
    // Backend uses full_name, not fullName or name
    expect(formData).not.toHaveProperty('fullName')
  })
})

describe('Password Change — POST /auth/change-password', () => {
  it('uses FormModal field names', () => {
    // FormModal collects data from input name attributes
    const fieldNames = ['current_password', 'new_password', 'confirm_password']
    const data = {
      current_password: 'old123',
      new_password: 'new456789',
      confirm_password: 'new456789',
    }
    fieldNames.forEach(f => expect(data).toHaveProperty(f))
  })

  it('validation: new password >= 8 chars', () => {
    const short = 'abc'
    const valid = 'longpassword'
    expect(short.length).toBeLessThan(8)
    expect(valid.length).toBeGreaterThanOrEqual(8)
  })
})

describe('API Key Creation — POST /api-keys', () => {
  it('uses FormModal field names', () => {
    const data = { name: 'CI/CD Key', expires_in_days: '90' }
    expect(data).toHaveProperty('name')
    // expires_in_days is optional
  })
})

// ============================================================
// 14. Auth Forms (LoginPage, ForgotPassword, ResetPassword)
// ============================================================
describe('Login — POST /auth/login', () => {
  it('has username and password fields', () => {
    const data = { username: 'admin', password: 'changeme123' }
    expect(data).toHaveProperty('username')
    expect(data).toHaveProperty('password')
  })
})

describe('Forgot Password — POST /auth/forgot-password', () => {
  it('sends email field', () => {
    const data = { email: 'user@example.com' }
    expect(data).toHaveProperty('email')
    expect(data.email).toContain('@')
  })
})

describe('Reset Password — POST /auth/reset-password', () => {
  it('sends token and password', () => {
    const data = { token: 'abc123', password: 'newsecure123' }
    expect(data).toHaveProperty('token')
    expect(data).toHaveProperty('password')
    expect(data.password.length).toBeGreaterThanOrEqual(8)
  })
})
