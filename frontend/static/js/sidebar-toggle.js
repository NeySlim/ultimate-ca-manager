/**
 * UCM Sidebar Collapsible Submenus
 * Handles expanding/collapsing sidebar submenu sections
 * COLLAPSE FEATURE DISABLED - ONLY SUBMENUS ACTIVE
 */

(function() {
    'use strict';

    // Sidebar collapse disabled for now - too many layout issues
    /*
    window.toggleSidebar = function() {
        const sidebar = document.getElementById('sidebar');
        const isCollapsed = sidebar.classList.contains('collapsed');
        
        if (isCollapsed) {
            sidebar.classList.remove('collapsed');
            localStorage.setItem('sidebar-collapsed', 'false');
        } else {
            sidebar.classList.add('collapsed');
            localStorage.setItem('sidebar-collapsed', 'true');
        }
        
        updateTooltipPositions();
    };

    function updateTooltipPositions() {
        const sidebar = document.getElementById('sidebar');
        if (!sidebar || !sidebar.classList.contains('collapsed')) {
            return;
        }

        const links = sidebar.querySelectorAll('.sidebar-link[data-tooltip]');
        links.forEach(link => {
            link.addEventListener('mouseenter', function(e) {
                const rect = this.getBoundingClientRect();
                this.style.setProperty('--tooltip-top', rect.top + 'px');
            });
        });
    }

    function initSidebarState() {
        const sidebar = document.getElementById('sidebar');
        const savedState = localStorage.getItem('sidebar-collapsed');
        
        if (savedState === 'true') {
            sidebar.classList.add('collapsed');
        }
        
        updateTooltipPositions();
    }
    */

    // Initialize collapsible submenus
    function initCollapsibleSubmenus() {
        // Get all parent links with submenus
        const parentLinks = document.querySelectorAll('.sidebar-link-parent');
        
        parentLinks.forEach(parentLink => {
            // Find the corresponding submenu
            const href = parentLink.getAttribute('href');
            const submenu = document.querySelector(`.sidebar-submenu[data-parent="${getParentKey(href)}"]`);
            
            if (!submenu) return;
            
            // Check if current path matches this section
            const isActive = parentLink.classList.contains('active');
            
            // Set initial state based on whether it's active
            if (isActive) {
                submenu.classList.add('expanded');
                const chevron = parentLink.querySelector('.sidebar-chevron');
                if (chevron) chevron.style.transform = 'rotate(180deg)';
            }
            
            // Add click handler to chevron only (not the whole link)
            const chevron = parentLink.querySelector('.sidebar-chevron');
            if (chevron) {
                chevron.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    toggleSubmenu(parentLink, submenu);
                });
            }
            
            // Store state in localStorage
            const storageKey = `sidebar-${getParentKey(href)}-expanded`;
            const savedState = localStorage.getItem(storageKey);
            
            if (savedState === 'true') {
                submenu.classList.add('expanded');
                const chevron = parentLink.querySelector('.sidebar-chevron');
                if (chevron) chevron.style.transform = 'rotate(180deg)';
            } else if (savedState === 'false') {
                submenu.classList.remove('expanded');
                const chevron = parentLink.querySelector('.sidebar-chevron');
                if (chevron) chevron.style.transform = 'rotate(0deg)';
            }
            
            // Flyout disabled for now
            /*
            parentLink.addEventListener('mouseenter', function() {
                const sidebar = document.getElementById('sidebar');
                if (sidebar.classList.contains('collapsed') && submenu) {
                    const rect = this.getBoundingClientRect();
                    submenu.style.setProperty('--flyout-top', rect.top + 'px');
                    submenu.classList.add('flyout');
                }
            });
            
            parentLink.addEventListener('mouseleave', function() {
                setTimeout(() => {
                    if (!submenu.matches(':hover')) {
                        submenu.classList.remove('flyout');
                    }
                }, 100);
            });
            
            if (submenu) {
                submenu.addEventListener('mouseleave', function() {
                    submenu.classList.remove('flyout');
                });
            }
            */
        });
    }
    
    // Toggle submenu visibility
    function toggleSubmenu(parentLink, submenu) {
        const isExpanded = submenu.classList.contains('expanded');
        const chevron = parentLink.querySelector('.sidebar-chevron');
        const href = parentLink.getAttribute('href');
        const storageKey = `sidebar-${getParentKey(href)}-expanded`;
        
        if (isExpanded) {
            // Collapse
            submenu.classList.remove('expanded');
            if (chevron) chevron.style.transform = 'rotate(0deg)';
            localStorage.setItem(storageKey, 'false');
        } else {
            // Expand
            submenu.classList.add('expanded');
            if (chevron) chevron.style.transform = 'rotate(180deg)';
            localStorage.setItem(storageKey, 'true');
        }
    }
    
    // Get parent key from href
    function getParentKey(href) {
        if (href.includes('/ca')) return 'ca';
        if (href.includes('/certificates')) return 'certificates';
        if (href.includes('/scep')) return 'scep';
        return href.replace(/^\//, '');
    }
    
    // Initialize on page load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            // initSidebarState(); // Disabled
            initCollapsibleSubmenus();
        });
    } else {
        // initSidebarState(); // Disabled
        initCollapsibleSubmenus();
    }
    
    // Re-initialize after HTMX swaps (in case sidebar is swapped)
    document.body.addEventListener('htmx:afterSettle', function(evt) {
        // Only reinit if sidebar was affected
        if (evt.target.classList && evt.target.classList.contains('sidebar-nav')) {
            initCollapsibleSubmenus();
        }
    });

})();
