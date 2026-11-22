/** A long value (a DNS name, a serial, a digest, a DN) that wraps after its separators before anywhere else. */
import { Fragment } from 'react'

const AFTER = /(?<=[.:/@,=_-])/

export function Breakable({ text }) {
  if (typeof text !== 'string' || text.length < 2) return text ?? null
  return text.split(AFTER).map((part, i) => <Fragment key={i}>{i > 0 && <wbr />}{part}</Fragment>)
}

export default Breakable
