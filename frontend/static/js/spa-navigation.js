/**
 * SPA-like Navigation for UCM
 * Handles HTMX navigation with sidebar state management
 */

// Update active sidebar link based on current URL
function updateActiveSidebarLink(url) {
    const path = new URL(url, window.location.origin).pathname;
    
    // Remove all active classes
    document.querySelectorAll('.sidebar-link').forEach(link => {
        link.classList.remove('active');
    });
    
    // Add active class to matching link
    document.querySelectorAll('.sidebar-link').forEach(link => {
        const href = link.getAttribute('href');
        if (href === path || (href !== '/' && path.startsWith(href))) {
            link.classList.add('active');
        }
    });
}

// Listen for HTMX response errors (401 = session expired)
document.addEventListener('htmx:responseError', function(event) {
    if (event.detail.xhr && event.detail.xhr.status === 401) {
        // Session expired - redirect to login
        window.location.href = '/logout?expired=1';
    }
});

// Listen for HTMX navigation events
document.addEventListener('htmx:afterSwap', function(event) {
    // Update active link
    if (event.detail.pathInfo && event.detail.pathInfo.finalRequestPath) {
        updateActiveSidebarLink(event.detail.pathInfo.finalRequestPath);
    }
    
    // Replace FontAwesome icons in new content
    if (window.ucmIcons) {
        setTimeout(() => {
            window.ucmIcons.replaceFontAwesomeIcons();
        }, 10);
    }
    
    // Reinitialize Alpine.js components in new content if needed
    if (window.Alpine && event.detail.target.id === 'main-content') {
        window.Alpine.initTree(event.detail.target);
    }
});

// Listen for browser back/forward
document.addEventListener('htmx:pushedIntoHistory', function(event) {
    updateActiveSidebarLink(event.detail.path);
});

// Handle popstate (browser back/forward buttons)
window.addEventListener('popstate', function(event) {
    updateActiveSidebarLink(window.location.pathname);
});
