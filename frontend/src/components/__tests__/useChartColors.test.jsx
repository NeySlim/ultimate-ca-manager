import { describe, it, expect, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useChartColors } from '../DashboardChart'

const root = document.documentElement
let style

function setPalette(css) {
  style?.remove()
  style = document.createElement('style')
  style.textContent = css
  document.head.appendChild(style)
}

afterEach(() => {
  style?.remove()
  root.removeAttribute('data-theme')
  root.removeAttribute('data-mode')
})

describe('useChartColors', () => {
  it('re-reads the colours when data-theme or data-mode change', async () => {
    setPalette(`
      :root[data-theme="a"][data-mode="dark"] { --accent-primary: #111111; --accent-pro: #aaaaaa; }
      :root[data-theme="a"][data-mode="light"] { --accent-primary: #222222; --accent-pro: #aaaaaa; }
      :root[data-theme="b"][data-mode="light"] { --accent-primary: #333333; --accent-pro: #bbbbbb; }`)
    root.setAttribute('data-theme', 'a')
    root.setAttribute('data-mode', 'dark')
    const { result } = renderHook(() => useChartColors())
    expect(result.current.primary).toBe('#111111')

    act(() => root.setAttribute('data-mode', 'light'))
    await waitFor(() => expect(result.current.primary).toBe('#222222'))

    act(() => root.setAttribute('data-theme', 'b'))
    await waitFor(() => expect(result.current.primary).toBe('#333333'))
    expect(result.current.pro).toBe('#bbbbbb')
  })
})
