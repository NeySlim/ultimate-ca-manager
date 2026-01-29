// Community version - Pro features not available
export const useLicense = () => ({ isPro: false, loading: false, type: 'community' })
export const useProFeatures = () => ({ isPro: false, loading: false })
export const ProBadge = () => null
export const ProFeatureGate = ({ children }) => null
