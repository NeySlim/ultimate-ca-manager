/**
 * The pieces SET3 adds to the mockup's form: a password's strength in the mockup's gauge (the
 * certificate validity bar) with its level in words, a PEM field that also reads a file (text
 * kept, a binary file shown by its size and removable), a settings test that only reads, the
 * section kept in ?tab= with the focus on its title, and the hidden-CA link drawn as a text link.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => (o ? `${k}:${Object.values(o).join(',')}` : k) }),
}))
const strength = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock('../../../lib/passwordStrength', async (orig) => ({ ...(await orig()), fetchPasswordStrength: strength.fetch }))

import { Input, PemField } from '../Form'
import { SettingsTest } from '../SettingsView'
import { useSectionParam } from '../useSectionParam'
import { Zone } from '../Zone'
import { HiddenCasToggle } from '../../cas/HiddenCasToggle'

describe('the strength of a password', () => {
  beforeEach(() => { strength.fetch.mockReset() })

  it('reads the offline level at once, then the server one, in the gauge and in words', async () => {
    strength.fetch.mockResolvedValue({ score: 90, level: 'strong', feedback: [] })
    render(<Input id="pw" label="New" type="password" showStrength onChange={() => {}} />)
    const box = screen.getByLabelText('New')
    expect(document.querySelector('.progress')).toBeNull()
    fireEvent.change(box, { target: { value: 'abc' } })
    // the local heuristic: weak, a warning gauge a quarter long
    const gauge = document.querySelector('.field > .progress')
    expect(gauge).toHaveClass('warn')
    expect(gauge.firstChild.style.width).toBe('25%')
    expect(gauge).toHaveAttribute('role', 'img')
    expect(gauge).toHaveAttribute('aria-label', 'passwordStrength.reading:passwordStrength.weak')
    expect(box).toHaveAccessibleDescription('passwordStrength.reading:passwordStrength.weak')
    await waitFor(() => expect(document.querySelector('.progress')).not.toHaveClass('warn'))
    expect(document.querySelector('.progress').firstChild.style.width).toBe('100%')
    expect(screen.getByText('passwordStrength.reading:passwordStrength.strong').tagName).toBe('SMALL')
    expect(strength.fetch).toHaveBeenCalledWith('abc')
  })

  it('reads a controlled value too, and nothing for a field without showStrength', async () => {
    strength.fetch.mockResolvedValue({ score: 60, level: 'good', feedback: [] })
    const { rerender } = render(<Input id="pw" label="New" type="password" showStrength value="Tr0ub4dor&3" onChange={() => {}} />)
    await waitFor(() => expect(document.querySelector('.progress span').style.width).toBe('75%'))
    rerender(<Input id="pw" label="New" type="password" value="Tr0ub4dor&3" onChange={() => {}} />)
    expect(document.querySelector('.progress')).toBeNull()
  })
})

describe('a PEM field that reads a file', () => {
  const file = (bytes, name) => new File([bytes], name)

  it('puts the text of a PEM file in the field and names the file to its owner', async () => {
    const onChange = vi.fn()
    const onFile = vi.fn()
    render(<PemField id="pem" label="PEM" value="" onChange={onChange} onFile={onFile} accept=".pem" />)
    expect(screen.getByLabelText('PEM').tagName).toBe('TEXTAREA')
    const picker = screen.getByLabelText('common.chooseFile')
    expect(picker.closest('label')).toHaveClass('text-link')
    const pem = file('-----BEGIN CERTIFICATE-----\nAA\n-----END CERTIFICATE-----\n', 'a.pem')
    await act(async () => { fireEvent.change(picker, { target: { files: [pem] } }) })
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('-----BEGIN CERTIFICATE-----\nAA\n-----END CERTIFICATE-----\n'))
    expect(onFile).toHaveBeenCalledWith(pem, expect.any(String))
  })

  it('reads a file dropped on the textarea as one picked', async () => {
    const onChange = vi.fn()
    render(<PemField id="pem" label="PEM" value="" onChange={onChange} />)
    const pem = file('-----BEGIN CERTIFICATE REQUEST-----\n', 'a.csr')
    await act(async () => { fireEvent.drop(screen.getByLabelText('PEM'), { dataTransfer: { files: [pem], types: ['Files'] } }) })
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('-----BEGIN CERTIFICATE REQUEST-----\n'))
  })

  it('sends a binary file as BASE64:, shows its size instead of the text and removes it on demand', async () => {
    const onChange = vi.fn()
    const { rerender } = render(<PemField id="pem" label="PEM" value="" onChange={onChange} />)
    await act(async () => { fireEvent.change(screen.getByLabelText('common.chooseFile'), { target: { files: [file(new Uint8Array([0x30, 0x82, 0x01]), 'a.der')] } }) })
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('BASE64:MIIB'))
    rerender(<PemField id="pem" label="PEM" value="BASE64:MIIB" onChange={onChange} />)
    expect(document.querySelector('textarea')).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('tools.binaryFileLoadedSize:3')
    fireEvent.click(screen.getByRole('button', { name: 'tools.removeFile' }))
    expect(onChange).toHaveBeenLastCalledWith('')
  })
})

describe('a settings test that only reads', () => {
  it('stays out of the write guard', () => {
    const { rerender } = render(<SettingsTest id="a" label="Run" hint="h" onTest={() => {}} write={false} />)
    expect(screen.getByRole('button', { name: 'Run' })).not.toHaveAttribute('data-write')
    rerender(<SettingsTest id="a" label="Run" hint="h" onTest={() => {}} />)
    expect(screen.getByRole('button', { name: 'Run' })).toHaveAttribute('data-write', '')
  })
})

function Sections({ stacked, ready = true }) {
  const [current, select] = useSectionParam(['a', 'b'], 'a', { stacked, ready })
  return (
    <>
      <p data-testid="current">{current}</p>
      {['a', 'b'].map((id) => (
        <section key={id} id={`set-sec-${id}`}><h2 id={`set-title-${id}`} tabIndex={-1}>{id}</h2></section>
      ))}
      <button type="button" onClick={() => select('b')}>to-b</button>
      <button type="button" onClick={() => select('a')}>to-a</button>
    </>
  )
}

describe('the section kept in ?tab=', () => {
  let scrolled
  beforeEach(() => { scrolled = []; Element.prototype.scrollIntoView = vi.fn(function s() { scrolled.push(this.id) }) })
  afterEach(() => { delete Element.prototype.scrollIntoView })

  it('lands a link on its frame quietly, once the frames are there', () => {
    const { rerender } = render(<MemoryRouter initialEntries={['/x?tab=b']}><Sections stacked ready={false} /></MemoryRouter>)
    expect(scrolled).toEqual([])
    rerender(<MemoryRouter initialEntries={['/x?tab=b']}><Sections stacked /></MemoryRouter>)
    expect(scrolled).toEqual(['set-sec-b'])
    expect(document.getElementById('set-title-b')).toHaveFocus()
    expect(document.getElementById('set-title-b')).toHaveAttribute('data-quiet-focus')
  })

  it('jumps a stacked page to a chosen section, its title focused without the quiet mark', () => {
    render(<MemoryRouter initialEntries={['/x']}><Sections stacked /></MemoryRouter>)
    expect(document.activeElement).toBe(document.body)
    fireEvent.click(screen.getByText('to-b'))
    expect(screen.getByTestId('current')).toHaveTextContent('b')
    expect(document.getElementById('set-title-b')).toHaveFocus()
    expect(document.getElementById('set-title-b')).not.toHaveAttribute('data-quiet-focus')
  })

  it('focuses the title of the one section shown once it is drawn, and the fallback drops the parameter', () => {
    render(<MemoryRouter initialEntries={['/x']}><Sections stacked={false} /></MemoryRouter>)
    expect(document.activeElement).toBe(document.body)
    fireEvent.click(screen.getByText('to-b'))
    expect(document.getElementById('set-title-b')).toHaveFocus()
    fireEvent.click(screen.getByText('to-a'))
    expect(screen.getByTestId('current')).toHaveTextContent('a')
    expect(document.getElementById('set-title-a')).toHaveFocus()
  })
})

describe('the link to the CAs hidden from issuance', () => {
  it('is the mockup text link under a zone, the product link elsewhere', () => {
    const { unmount } = render(<MemoryRouter><Zone><HiddenCasToggle count={2} shown={false} onToggle={() => {}} /></Zone></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'cas.showHiddenCas:2' })).toHaveClass('text-link')
    unmount()
    render(<HiddenCasToggle count={2} shown={false} onToggle={() => {}} />)
    expect(screen.getByRole('button', { name: 'cas.showHiddenCas:2' })).not.toHaveClass('text-link')
  })
})
