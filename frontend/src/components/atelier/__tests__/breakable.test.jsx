/** A long value wraps after its separators (a DNS name, a serial, a DN) before anywhere else. */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Breakable } from '../Breakable'

describe('Breakable', () => {
  it('puts a break opportunity after each separator, the text unchanged', () => {
    const { container } = render(<p><Breakable text="20:01:AB" /> <Breakable text="a.example.com" /></p>)
    expect(container.textContent).toBe('20:01:AB a.example.com')
    expect(container.querySelectorAll('wbr')).toHaveLength(4)
    expect(container.querySelector('p').innerHTML).toBe('20:<wbr>01:<wbr>AB a.<wbr>example.<wbr>com')
  })

  it('leaves a value without separator, or not a text, as it is', () => {
    const { container } = render(<p><Breakable text="ABCDEF0123" /><Breakable text={null} /><Breakable text={<b>x</b>} /></p>)
    expect(container.innerHTML).toBe('<p>ABCDEF0123<b>x</b></p>')
  })
})
