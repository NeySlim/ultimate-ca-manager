/**
 * Findings of damaged cross-certificate records: explicit repairs only, offered per permission (#400).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('../../../lib/utils', () => ({ cn: (...a) => a.filter(Boolean).join(' ') }))

import { ChainRepairBar } from '../ChainRepairBar'

const t = (key, vars) => (vars?.name ? `${key}:${vars.name}` : key)
const shadowed = { kind: 'shadowed_root', ca_id: 5, ca_name: 'Dup', root_id: 2, root_name: 'Root', subject: 'CN=Root', actions: ['convert_to_cross'] }
const sameKey = { kind: 'same_key_distinct_certs', ca_ids: [7, 8], subject: 'CN=Root', actions: ['restore_primary'] }

const bar = (props) => (
  <ChainRepairBar data={{ task: {}, stats: { total_cas: 3 } }} running={false} onRun={() => {}} canRunRepair t={t} {...props} />
)

describe('ChainRepairBar cross-certificate findings', () => {
  it('is silent without findings', () => {
    render(bar({ findings: [] }))
    expect(screen.queryByText('crossCerts.findings')).toBeNull()
  })

  it('lists the findings once expanded and runs the conversion', () => {
    const onConvert = vi.fn()
    render(bar({ findings: [shadowed], canConvert: true, onConvert }))
    expect(screen.queryByTestId('cross-finding')).toBeNull()
    fireEvent.click(screen.getByText('crossCerts.findings'))
    expect(screen.getByTestId('cross-finding')).toBeInTheDocument()
    fireEvent.click(screen.getByText('crossCerts.convertToCross'))
    expect(onConvert).toHaveBeenCalledWith(shadowed)
  })

  it('offers restore-primary once per record of a collision', () => {
    const onRestore = vi.fn()
    render(bar({ findings: [sameKey], canRestore: true, onRestore, caName: (id) => `ca${id}` }))
    fireEvent.click(screen.getByText('crossCerts.findings'))
    fireEvent.click(screen.getByText('crossCerts.restorePrimaryOn:ca8'))
    expect(onRestore).toHaveBeenCalledWith(sameKey, 8)
    expect(screen.queryByText('crossCerts.convertToCross')).toBeNull()
  })

  it('hides the repairs from a user who may not run them', () => {
    render(bar({ findings: [shadowed, sameKey], canConvert: false, canRestore: false }))
    fireEvent.click(screen.getByText('crossCerts.findings'))
    expect(screen.getAllByTestId('cross-finding')).toHaveLength(2)
    expect(screen.queryByText('crossCerts.convertToCross')).toBeNull()
    expect(screen.queryByText(/crossCerts.restorePrimaryOn/)).toBeNull()
  })
})
