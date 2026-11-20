/**
 * Helpers of the issue form tests: labels of its fields, and the two steps to an issuance.
 */
import { screen, within, fireEvent, waitFor } from '@testing-library/react'
import { beforeEach, expect } from 'vitest'
import { clearDrafts } from '../issue/issueDrafts'

// Drafts outlive a form: each test starts without the one a previous test left
beforeEach(() => clearDrafts())

export const P = 'certificates.issueForm.'
export const LABEL = {
  template: `${P}template`,
  ca: `${P}authority`,
  cn: `${P}commonName`,
  key: `${P}keyAlgorithm`,
  days: `${P}validityDays`,
  certType: 'certificates.certType',
  hybridClassical: 'certificates.hybrid.classical',
  hybridPq: 'certificates.hybrid.pq',
}

export const field = (label) => screen.getByLabelText(label)
export const optionValues = (label) => within(field(label)).getAllByRole('option').map((o) => o.value)
export const choose = (label, value) => fireEvent.change(field(label), { target: { value } })
export const type = (label, value) => fireEvent.change(field(label), { target: { value } })
export const openAdvanced = () => fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}advanced`) }))

/** Step 1 to step 2: the Review step shows. */
export async function toReview() {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
  return screen.findByTestId('issue-review')
}

/** Configure, Review, Issue: resolves to the body handed to onSubmit. */
export async function reviewAndIssue(onSubmit) {
  const calls = onSubmit.mock.calls.length
  await toReview()
  fireEvent.click(screen.getByTestId('issue-submit'))
  await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(calls + 1))
  return onSubmit.mock.calls[calls][0]
}
