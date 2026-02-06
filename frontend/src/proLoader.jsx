/**
 * Dynamic Pro Feature Loader
 * 
 * Uses import.meta.glob to dynamically detect and load Pro pages/modules.
 * Works in both Pro and Community editions without build errors.
 */
import { lazy } from 'react'
import { Navigate } from 'react-router-dom'

// Dynamically discover Pro modules at build time
// These return empty objects in Community edition (no pro/ folder)
const proPageModules = import.meta.glob('./pro/pages/*.jsx')
const proModules = import.meta.glob('./pro/*.js')

// Check if main Pro index exists
const proIndexPath = './pro/index.js'
const hasProIndex = !!proModules[proIndexPath]

// Fallback component for missing Pro pages
const ProFallback = () => <Navigate to="/" replace />

/**
 * Creates a lazy-loaded Pro page component
 * Returns fallback if page doesn't exist (Community edition)
 */
export function createProPage(pageName) {
  const modulePath = `./pro/pages/${pageName}.jsx`
  
  if (proPageModules[modulePath]) {
    return lazy(() => 
      proPageModules[modulePath]()
        .catch(() => ({ default: ProFallback }))
    )
  }
  
  // Page doesn't exist - return a component that renders fallback
  return () => <ProFallback />
}

/**
 * Load Pro settings categories (for SettingsPage)
 * Returns empty array in Community edition
 */
export async function loadProSettings() {
  const modulePath = './pro/settings.js'
  if (proModules[modulePath]) {
    try {
      const module = await proModules[modulePath]()
      return module.proSettingsCategories || []
    } catch {
      return []
    }
  }
  return []
}

/**
 * Load Pro module (for Sidebar/AppShell detection)
 * Returns the module if available, throws if not (Community edition)
 */
export async function loadProModule() {
  if (hasProIndex && proModules[proIndexPath]) {
    return proModules[proIndexPath]()
  }
  throw new Error('Pro module not available')
}

/**
 * Check if Pro features are available (sync check at build time)
 */
export const hasProFeatures = Object.keys(proPageModules).length > 0

/**
 * List of available Pro pages (for debugging/UI)
 */
export const availableProPages = Object.keys(proPageModules).map(
  path => path.replace('./pro/pages/', '').replace('.jsx', '')
)

// Pre-created lazy components for common Pro pages
export const RBACPage = createProPage('RBACPage')
export const HSMPage = createProPage('HSMPage')
export const SecurityDashboardPage = createProPage('SecurityDashboardPage')
export const SSOPage = createProPage('SSOPage')
