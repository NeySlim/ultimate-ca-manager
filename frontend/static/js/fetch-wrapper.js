/**
 * UCM Fetch Wrapper
 * Auto-handles JWT token injection and session refresh
 * Drop-in replacement for fetch()
 */

// Store original fetch
const originalFetch = window.fetch;

/**
 * Get valid JWT token from session/cookie
 */
function getJWTToken() {
    // Try to get from meta tag (set by Flask)
    const meta = document.querySelector('meta[name="jwt-token"]');
    if (meta) {
        return meta.getAttribute('content');
    }
    
    // Fallback: try from cookie (set by Flask-JWT-Extended)
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'access_token_cookie') {
            return value;
        }
    }
    
    return null;
}

/**
 * Enhanced fetch with automatic JWT injection
 * Usage: Same as native fetch()
 */
window.fetch = function(url, options = {}) {
    // Clone options to avoid mutations
    const enhancedOptions = { ...options };
    enhancedOptions.headers = { ...(options.headers || {}) };
    
    // Auto-inject JWT token for API calls
    if (url.includes('/api/v1/') || url.includes('/api/auth/')) {
        const token = getJWTToken();
        if (token && !enhancedOptions.headers['Authorization']) {
            enhancedOptions.headers['Authorization'] = `Bearer ${token}`;
        }
    }
    
    // Auto-inject CSRF token for POST/PUT/DELETE
    const method = (enhancedOptions.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        if (csrfMeta && !enhancedOptions.headers['X-CSRF-Token']) {
            enhancedOptions.headers['X-CSRF-Token'] = csrfMeta.getAttribute('content');
        }
    }
    
    // Call original fetch
    return originalFetch(url, enhancedOptions)
        .then(response => {
            // Handle 401 Unauthorized - session expired
            if (response.status === 401) {
                // Trigger session expiration warning
                if (typeof window.SessionManager !== 'undefined') {
                    window.SessionManager.handleExpiredSession();
                } else {
                    // Fallback: redirect to login
                    console.warn('Session expired, redirecting to login');
                    window.location.href = '/login?expired=1';
                }
                throw new Error('Session expired');
            }
            
            return response;
        });
};

// Export for modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { fetch: window.fetch, getJWTToken };
}

console.log('✅ UCM Fetch Wrapper loaded - JWT auto-injection enabled');
