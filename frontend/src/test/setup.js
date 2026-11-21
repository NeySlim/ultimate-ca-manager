import '@testing-library/jest-dom'
import { vi, afterEach } from 'vitest'
import { dropAllDrafts } from '../lib/draftMemory'

// Drafts kept for the tab live in module memory: none passes from one test to the next
afterEach(() => dropAllDrafts())

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// Mock ResizeObserver. A class, not an arrow returning an object: the real one is
// called with `new`, and a mock that cannot be constructed fails only in the
// components that observe something.
global.ResizeObserver = class ResizeObserver {
  constructor(callback) { this.callback = callback }
  observe() {}
  unobserve() {}
  disconnect() {}
}

// Mock IntersectionObserver
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))
