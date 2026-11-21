/**
 * The terms of a search marked in what the help renders: on its text nodes (the strings of the
 * React tree), never in its Markdown, so links, code and tables keep their shape.
 */
import { Fragment, cloneElement, isValidElement } from 'react'
import { termRanges } from './search'

/** A string with its terms in `mark.guide-hit`; the string itself when none occurs. */
export function markText(text, terms, key) {
  const ranges = termRanges(text, terms)
  if (!ranges.length) return text
  const parts = []
  let at = 0
  ranges.forEach(([a, b], i) => {
    if (a > at) parts.push(text.slice(at, a))
    parts.push(<mark key={i} className="guide-hit">{text.slice(a, b)}</mark>)
    at = b
  })
  if (at < text.length) parts.push(text.slice(at))
  return <Fragment key={key}>{parts}</Fragment>
}

/** A rendered tree with its terms marked; element types, props and keys unchanged. */
export function highlightTree(node, terms, key) {
  if (!terms?.length || node == null || typeof node === 'boolean') return node
  if (typeof node === 'string') return markText(node, terms, key)
  if (Array.isArray(node)) return node.map((child, i) => highlightTree(child, terms, isValidElement(child) ? child.key : `t${i}`))
  if (!isValidElement(node) || node.props.children == null) return node
  return cloneElement(node, undefined, highlightTree(node.props.children, terms, 't0'))
}
