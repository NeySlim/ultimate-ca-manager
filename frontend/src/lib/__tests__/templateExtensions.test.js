import { describe, it, expect } from 'vitest'
import {
  buildExtensionsTemplate, qcFormFromStored, qcPayloadFromForm, parsePolicyOids, emptyQcForm,
} from '../templateExtensions'

const base = { key_usage: ['digitalSignature'], extended_key_usage: [], san_types: ['dns'], qc: emptyQcForm(), policy_oids: '' }

describe('buildExtensionsTemplate', () => {
  it('keeps keys the form does not edit', () => {
    const existing = { key_usage: ['x'], custom_flag: { a: 1 }, name_constraints: ['y'] }
    const out = buildExtensionsTemplate(existing, base)
    expect(out.custom_flag).toEqual({ a: 1 })
    expect(out.name_constraints).toEqual(['y'])
    expect(out.key_usage).toEqual(['digitalSignature'])
    expect(out.basic_constraints).toEqual({ ca: false })
  })

  it('round-trips a stored qc_statements and policy OIDs', () => {
    const stored = {
      qc_statements: { compliance: true, type: 'esign', sscd: true, pds: [{ url: 'https://x.example/pds', language: 'en' }],
        retention_period: 10, limit_value: { currency: 'EUR', amount: 100, exponent: 0 }, semantics: 'eidas-natural' },
      certificate_policies: ['0.4.0.194112.1.2'],
    }
    const out = buildExtensionsTemplate(stored, {
      ...base, qc: qcFormFromStored(stored.qc_statements), policy_oids: stored.certificate_policies.join('\n'),
    })
    expect(out.qc_statements).toEqual(stored.qc_statements)
    expect(out.certificate_policies).toEqual(['0.4.0.194112.1.2'])
  })

  it('drops qc_statements and policies once cleared', () => {
    const out = buildExtensionsTemplate({ qc_statements: { sscd: true }, certificate_policies: ['1.2.3'] }, base)
    expect('qc_statements' in out).toBe(false)
    expect('certificate_policies' in out).toBe(false)
  })
})

describe('qcPayloadFromForm', () => {
  it('is null for an empty form', () => expect(qcPayloadFromForm(emptyQcForm())).toBeNull())

  it('normalises country codes, language and currency', () => {
    const f = { ...emptyQcForm(), cc_legislation: 'fr, de', pds: [{ url: ' https://a.example ', language: 'EN' }, { url: '', language: '' }],
      limit_currency: 'eur', limit_amount: '5000', limit_exponent: '0' }
    expect(qcPayloadFromForm(f)).toEqual({
      cc_legislation: ['FR', 'DE'],
      pds: [{ url: 'https://a.example', language: 'en' }],
      limit_value: { currency: 'EUR', amount: 5000, exponent: 0 },
    })
  })
})

describe('parsePolicyOids', () => {
  it('splits and dedups', () => {
    expect(parsePolicyOids('1.2.3, 1.2.4\n1.2.3')).toEqual(['1.2.3', '1.2.4'])
  })
})
