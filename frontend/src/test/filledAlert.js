import { screen, waitFor } from '@testing-library/react'

/** The sign-in card's alert (`#login-error`, always there as a live region) once it holds a message. */
export const findAlert = () => waitFor(() => {
  const el = screen.getByRole('alert')
  if (!el.textContent) throw new Error('the alert is still empty')
  return el
})
