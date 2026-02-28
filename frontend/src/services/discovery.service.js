/**
 * Discovery Service
 * Handles certificate discovery API calls
 */
import { apiClient } from './apiClient'

export const discoveryService = {
    /**
     * Scan multiple targets for TLS certificates
     * @param {string[]} targets - List of target hostnames or IPs
     * @param {number[]} [ports=[443, 8443]] - List of ports to scan
     * @returns {Promise<Object>} - Scan results
     */
    scan: async (targets, ports = [443, 8443]) => {
        return apiClient.post('/discovery/scan', { targets, ports })
    },
    
    /**
     * Scan a subnet for TLS certificates
     * @param {string} subnet - Subnet in CIDR notation (e.g., '192.168.1.0/24')
     * @param {number[]} [ports=[443, 8443]] - List of ports to scan
     * @returns {Promise<Object>} - Scan results
     */
    scanSubnet: async (subnet, ports = [443, 8443]) => {
        return apiClient.post('/discovery/scan-subnet', { subnet, ports })
    },
    
    /**
     * Import discovered certificates into UCM
     * @param {Object[]} certificates - List of certificate objects
     * @returns {Promise<Object>} - Import results
     */
    import: async (certificates) => {
        return apiClient.post('/discovery/import', { certificates })
    },
    
    /**
     * Get discovery history
     * @param {number} [limit=100] - Maximum number of records to return
     * @returns {Promise<Object>} - Discovery history
     */
    getHistory: async (limit = 100) => {
        return apiClient.get('/discovery/history', { params: { limit } })
    },
    
    /**
     * Get certificates that are not in UCM
     * @returns {Promise<Object>} - Unknown certificates
     */
    getUnknown: async () => {
        return apiClient.get('/discovery/unknown')
    },
    
    /**
     * Get expired discovered certificates
     * @returns {Promise<Object>} - Expired certificates
     */
    getExpired: async () => {
        return apiClient.get('/discovery/expired')
    }
}
