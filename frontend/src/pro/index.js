/**
 * Pro Module Index
 * Exports all Pro components for dynamic loading
 */
export { default as RBACPage } from './pages/RBACPage'
export { default as HSMPage } from './pages/HSMPage'
export { ProBadge, ProFeatureGate } from './components/ProBadge'
export { useLicense, useProFeatures } from './hooks/useLicense'
export { proSettingsCategories } from './settings'
export { default as SSOSettingsSection } from './components/SSOSettingsSection'

// Pro routes configuration
export const proRoutes = [
  { path: '/rbac', component: 'RBACPage', label: 'RBAC', icon: 'Shield' },
  { path: '/hsm', component: 'HSMPage', label: 'HSM', icon: 'Lock' },
]

// Flag to indicate Pro module is present
export const PRO_MODULE_PRESENT = true
