/**
 * The browser half of the ACME client key type contract: the forms offer the
 * certificate key types the server accepts, and hide them as the server does.
 * `backend/tests/test_acme_client_key_types_contract.py` reads the same file.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { ACME_CLIENT_LABELS, findAlgorithm, listAlgorithms } from '../keyAlgorithms'

const here = dirname(fileURLToPath(import.meta.url))
const rows = JSON.parse(readFileSync(
  join(here, '..', '..', '..', '..', 'contracts', 'acme_client_key_types.json'), 'utf8')).cert_key_types

describe('ACME client key types agree with the server', () => {
  it('offers the contract types in its order', () => {
    expect(ACME_CLIENT_LABELS).toEqual(rows.map(r => r.label))
  })

  it.each(rows)('$label: FIPS and ML-DSA as the server says', (row) => {
    const algo = findAlgorithm(row.label)
    expect(algo.fips).toBe(row.fips)
    expect(algo.family === 'ML-DSA').toBe(row.ml_dsa)
  })

  it('hides what FIPS mode or a build without ML-DSA refuses', () => {
    const offered = (opts) => listAlgorithms({ labels: ACME_CLIENT_LABELS, ...opts }).map(a => a.label)
    expect(offered({ fips: true })).toEqual(rows.filter(r => r.fips).map(r => r.label))
    const approved = rows.filter(r => r.fips !== false).map(r => r.label)
    expect(offered({ fips: true, fipsKeys: approved })).toEqual(approved)
    expect(offered({ mldsa: false })).toEqual(rows.filter(r => !r.ml_dsa).map(r => r.label))
  })
})
