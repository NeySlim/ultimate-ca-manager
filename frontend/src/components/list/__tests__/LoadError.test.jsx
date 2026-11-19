/**
 * A list that could not be read: an alert with what failed, the cause and a button that
 * tries again.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))

import { LoadError } from '../LoadError'

describe('LoadError', () => {
  it('announces the failure with its cause and retries on demand', () => {
    const onRetry = vi.fn()
    render(<LoadError title="The things could not be loaded" cause="Cause: 503." onRetry={onRetry} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('The things could not be loaded')
    expect(alert).toHaveTextContent('Cause: 503.')
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('The things could not be loaded')
    fireEvent.click(screen.getByRole('button', { name: 'common.retry' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
