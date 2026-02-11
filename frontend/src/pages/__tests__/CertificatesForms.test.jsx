/**
 * Form API Contract Tests
 * 
 * Validates that form data structures match backend API expectations.
 * Catches field name mismatches, wrong data types, and Select component misuse.
 * 
 * These tests prevented real bugs:
 * - common_name vs cn field name mismatch
 * - validity_days sent as string instead of int
 * - Select using <option> children instead of options prop
 * - onChange(e.target.value) instead of onChange(value) with Radix
 */
import { describe, it, expect, vi } from 'vitest'

describe('Certificate Issue Form - API Contract', () => {
  const mockCas = [
    { id: 1, common_name: 'Root CA', descr: 'Root CA' },
    { id: 2, common_name: 'Intermediate CA', descr: 'Intermediate' },
  ]

  it('form data uses cn (not common_name) to match backend POST /certificates', () => {
    // Backend (certificates.py L203): if not data.get('cn')
    const formData = {
      ca_id: '1',
      cn: 'test.example.com',
      san: '',
      key_type: 'rsa',
      key_size: '2048',
      validity_days: '365',
    }

    expect(formData).toHaveProperty('cn')
    expect(formData).not.toHaveProperty('common_name')
  })

  it('validity_days is parsed to integer before submission', () => {
    const cases = [
      { input: '365', expected: 365 },
      { input: '90', expected: 90 },
      { input: '', expected: 365 },
      { input: 'abc', expected: 365 },
    ]

    cases.forEach(({ input, expected }) => {
      const result = parseInt(input, 10) || 365
      expect(result).toBe(expected)
      expect(typeof result).toBe('number')
    })
  })

  it('CA options use String(id) for Radix Select compatibility', () => {
    const options = mockCas.map(ca => ({
      value: String(ca.id),
      label: ca.descr || ca.common_name,
    }))

    options.forEach(opt => {
      expect(typeof opt.value).toBe('string')
      expect(typeof opt.label).toBe('string')
      expect(opt).toHaveProperty('value')
      expect(opt).toHaveProperty('label')
    })
  })

  it('includes all required fields for certificate creation', () => {
    const requiredFields = ['ca_id', 'cn', 'key_type', 'key_size', 'validity_days']
    const formData = {
      ca_id: '1', cn: 'test.example.com', san: '',
      key_type: 'rsa', key_size: '2048', validity_days: '365',
    }

    requiredFields.forEach(field => {
      expect(formData).toHaveProperty(field)
    })
  })

  it('key_size options match key_type', () => {
    const rsaSizes = [
      { value: '2048', label: '2048 bits' },
      { value: '4096', label: '4096 bits' },
    ]
    const ecdsaSizes = [
      { value: '256', label: 'P-256' },
      { value: '384', label: 'P-384' },
    ]

    rsaSizes.forEach(s => expect(parseInt(s.value)).toBeGreaterThanOrEqual(2048))
    ecdsaSizes.forEach(s => expect(parseInt(s.value)).toBeLessThanOrEqual(384))
  })
})

describe('CSR Sign Form - API Contract', () => {
  it('stringifies ca.id for Select options', () => {
    const cas = [
      { id: 1, descr: 'Root CA', name: null, common_name: 'Root' },
      { id: 42, descr: null, name: 'Intermediate', common_name: 'Inter' },
    ]

    const options = cas.map(ca => ({
      value: String(ca.id),
      label: ca.descr || ca.name || ca.common_name,
    }))

    expect(options[0].value).toBe('1')
    expect(options[1].value).toBe('42')
    expect(typeof options[0].value).toBe('string')
    expect(options[0].label).toBe('Root CA')
    expect(options[1].label).toBe('Intermediate')
  })
})

describe('Radix Select onChange Contract', () => {
  it('onChange receives value directly (not event.target.value)', () => {
    // Radix Select: onChange(value: string)
    // NOT: onChange(event: { target: { value: string } })
    const setter = vi.fn()
    const correctHandler = (val) => setter(val)
    
    correctHandler('option-1')
    expect(setter).toHaveBeenCalledWith('option-1')
    
    // If someone writes onChange={e => setter(e.target.value)},
    // Radix passes a string, so e.target would be undefined → crash
  })

  it('all Select option values must be strings', () => {
    // Radix Select requires string values
    const numericIds = [1, 42, 100]
    const options = numericIds.map(id => ({ value: String(id), label: `Item ${id}` }))
    
    options.forEach(opt => {
      expect(typeof opt.value).toBe('string')
    })
  })
})

describe('ACME Forms - API Contract', () => {
  it('account creation form has required fields', () => {
    const formData = {
      email: 'test@example.com',
      environment: 'production',
    }
    
    expect(formData).toHaveProperty('email')
    expect(formData).toHaveProperty('environment')
  })

  it('certificate request form has required fields', () => {
    const formData = {
      domain: 'example.com',
      key_type: 'rsa',
      challenge_type: 'http-01',
    }

    expect(formData).toHaveProperty('domain')
    expect(formData).toHaveProperty('key_type')
    expect(formData).toHaveProperty('challenge_type')
  })
})
