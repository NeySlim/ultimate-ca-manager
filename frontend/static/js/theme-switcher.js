/**
 * Theme Switcher for UCM
 * Manages theme switching between Light/Dark variants
 */

// Get current theme from localStorage or default to sentinel-light
function getCurrentTheme() {
    return localStorage.getItem('ucm-theme') || 'sentinel-light';
}

// Get current theme variant (light/dark)
function getThemeVariant(theme) {
    if (!theme) theme = getCurrentTheme();
    return theme.endsWith('-dark') ? 'dark' : 'light';
}

// Get theme base name (sentinel, amber, nebula)
function getThemeBase(theme) {
    if (!theme) theme = getCurrentTheme();
    return theme.replace(/-light$|-dark$/, '');
}

// Set theme
function setTheme(themeName) {
    localStorage.setItem('ucm-theme', themeName);
    
    // Update data-theme attribute FIRST to prevent flash
    document.documentElement.setAttribute('data-theme', themeName);
    
    // Update stylesheet link
    const themeLink = document.getElementById('theme-css');
    if (themeLink) {
        themeLink.href = `/static/css/themes/${themeName}.css`;
    }
    
    // Update icon in toggle button
    updateThemeIcon();
    
    // Update active theme indicator in dropdown
    updateActiveThemeIndicator(themeName);
    
    // Notify icon system of theme change
    if (window.ucmIcons) {
        window.ucmIcons.updateTheme(themeName);
    }
}

// Update active theme indicator in dropdown menu
function updateActiveThemeIndicator(themeName) {
    // Remove all active indicators
    document.querySelectorAll('[data-action="set-theme"]').forEach(item => {
        const icon = item.querySelector('.theme-active-icon');
        if (icon) {
            icon.remove();
        }
        item.style.fontWeight = '';
        item.style.background = '';
    });
    
    // Add indicator to current theme
    const activeItem = document.querySelector(`[data-action="set-theme"][data-theme="${themeName}"]`);
    if (activeItem) {
        activeItem.style.fontWeight = '600';
        activeItem.style.background = 'var(--bg-hover)';
        
        // Add checkmark icon
        const checkIcon = document.createElement('i');
        checkIcon.className = 'fas fa-check theme-active-icon';
        checkIcon.style.marginLeft = 'auto';
        checkIcon.style.color = 'var(--primary-color)';
        activeItem.appendChild(checkIcon);
    }
}

// Switch to specific theme (called from dropdown)
function switchTheme(themeName) {
    setTheme(themeName);
}

// Toggle between light and dark for current theme
function toggleThemeVariant() {
    const base = getThemeBase();
    const currentVariant = getThemeVariant();
    const newVariant = currentVariant === 'light' ? 'dark' : 'light';
    const newTheme = `${base}-${newVariant}`;
    
    setTheme(newTheme);
}

// Update theme toggle icon
function updateThemeIcon() {
    const variant = getThemeVariant();
    const icon = document.getElementById('theme-icon');
    
    if (icon) {
        // Update SVG use href instead of className
        const useElement = icon.querySelector('use');
        if (useElement) {
            useElement.setAttribute('href', variant === 'dark' ? '#icon-sun' : '#icon-moon');
        }
    }
}

// Initialize theme icon on page load
document.addEventListener('DOMContentLoaded', function() {
    updateThemeIcon();
    // Initialize active theme indicator
    const currentTheme = getCurrentTheme();
    updateActiveThemeIndicator(currentTheme);
});
