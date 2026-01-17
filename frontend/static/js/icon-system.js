/**
 * UCM Dynamic Icon System
 * Loads SVG icons with theme-adaptive gradients
 */

class IconSystem {
    constructor() {
        this.icons = null;
        this.gradients = null;
        this.currentTheme = null;
        this.svgCache = new Map();
    }

    async init() {
        try {
            // Try to load from localStorage cache first
            const cachedData = localStorage.getItem('ucm-icons-data');
            const cachedVersion = localStorage.getItem('ucm-icons-version');
            const currentVersion = '3.6'; // Increment this when icons.json changes
            
            if (cachedData && cachedVersion === currentVersion) {
                // Use cached data for instant load
                const data = JSON.parse(cachedData);
                this.icons = data.icons;
                this.gradients = data.gradients;
            } else {
                // Fetch and cache
                const response = await fetch(`/static/data/icons.json?v=${currentVersion}`);
                const data = await response.json();
                this.icons = data.icons;
                this.gradients = data.gradients;
                
                // Store in cache
                localStorage.setItem('ucm-icons-data', JSON.stringify(data));
                localStorage.setItem('ucm-icons-version', currentVersion);
            }
            
            // Determine current theme from localStorage (faster than DOM)
            this.currentTheme = localStorage.getItem('ucm-theme') || 'sentinel-light';
            
            // Inject gradient definitions into DOM immediately
            this.injectGradientDefs();
            
            console.log('✅ Icon system initialized with theme:', this.currentTheme);
            return true;
        } catch (error) {
            console.error('❌ Failed to initialize icon system:', error);
            return false;
        }
    }

    /**
     * Inject SVG gradient definitions and icon symbols into the document
     */
    injectGradientDefs() {
        // Remove existing gradient defs if any
        const existing = document.getElementById('ucm-gradient-defs');
        if (existing) {
            existing.remove();
        }

        // Create hidden SVG with gradient definitions and icon symbols
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.id = 'ucm-gradient-defs';
        svg.style.position = 'absolute';
        svg.style.width = '0';
        svg.style.height = '0';
        svg.setAttribute('aria-hidden', 'true');

        const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');

        // Get gradients for current theme
        const themeGradients = this.gradients[this.currentTheme] || this.gradients['sentinel-light'];

        // Create gradient elements
        for (const [type, colors] of Object.entries(themeGradients)) {
            const gradient = document.createElementNS('http://www.w3.org/2000/svg', 'linearGradient');
            gradient.id = `ucm-gradient-${type}`;
            gradient.setAttribute('x1', '0%');
            gradient.setAttribute('y1', '0%');
            gradient.setAttribute('x2', '100%');
            gradient.setAttribute('y2', '100%');

            // Stop 1
            const stop1 = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
            stop1.setAttribute('offset', '0%');
            stop1.setAttribute('stop-color', colors[0]);
            gradient.appendChild(stop1);

            // Stop 2
            const stop2 = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
            stop2.setAttribute('offset', '100%');
            stop2.setAttribute('stop-color', colors[1]);
            gradient.appendChild(stop2);

            defs.appendChild(gradient);
        }

        // Create icon symbols
        for (const [iconName, iconData] of Object.entries(this.icons)) {
            const symbol = document.createElementNS('http://www.w3.org/2000/svg', 'symbol');
            symbol.id = `icon-${iconName}`;
            symbol.setAttribute('viewBox', iconData.viewBox);

            // Add paths
            for (const pathData of iconData.paths) {
                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                if (pathData.d) path.setAttribute('d', pathData.d);
                
                // Set stroke/fill based on path data
                if (pathData.fill && pathData.fill !== 'none') {
                    if (pathData.fill === 'currentColor') {
                        path.setAttribute('fill', 'currentColor');
                    } else {
                        path.setAttribute('fill', `url(#ucm-gradient-${pathData.gradient})`);
                    }
                } else {
                    path.setAttribute('fill', 'none');
                }
                
                // Handle stroke - use gradient if stroke-width is defined
                if (pathData['stroke-width']) {
                    path.setAttribute('stroke', `url(#ucm-gradient-${pathData.gradient})`);
                    path.setAttribute('stroke-width', pathData['stroke-width']);
                    if (pathData['stroke-linecap']) path.setAttribute('stroke-linecap', pathData['stroke-linecap']);
                    if (pathData['stroke-linejoin']) path.setAttribute('stroke-linejoin', pathData['stroke-linejoin']);
                } else if (iconData.stroke) {
                    path.setAttribute('stroke', 'currentColor');
                }
                
                symbol.appendChild(path);
            }

            defs.appendChild(symbol);
        }

        svg.appendChild(defs);
        document.body.insertBefore(svg, document.body.firstChild);
    }

    /**
     * Get SVG icon as HTML string
     * @param {string} iconName - Name of the icon (e.g., 'dashboard', 'certificate')
     * @param {string} className - Optional CSS class
     * @param {number} size - Icon size in pixels (default: 24)
     * @returns {string} SVG HTML string
     */
    getIcon(iconName, className = '', size = 24) {
        const cacheKey = `${iconName}-${className}-${size}-${this.currentTheme}`;
        
        // Return from cache if available
        if (this.svgCache.has(cacheKey)) {
            return this.svgCache.get(cacheKey);
        }

        const iconData = this.icons[iconName];
        if (!iconData) {
            console.warn(`Icon "${iconName}" not found`);
            return '';
        }

        const paths = iconData.paths.map(pathData => {
            const opacity = pathData.opacity !== undefined ? ` opacity="${pathData.opacity}"` : '';
            const gradientRef = `url(#ucm-gradient-${pathData.gradient})`;
            
            // Handle stroke vs fill
            const fill = pathData.fill === 'none' ? 'none' : (pathData.fill === 'currentColor' ? 'currentColor' : gradientRef);
            const stroke = pathData['stroke-width'] ? gradientRef : 'none';
            const strokeWidth = pathData['stroke-width'] ? ` stroke-width="${pathData['stroke-width']}"` : '';
            const strokeLinecap = pathData['stroke-linecap'] ? ` stroke-linecap="${pathData['stroke-linecap']}"` : '';
            const strokeLinejoin = pathData['stroke-linejoin'] ? ` stroke-linejoin="${pathData['stroke-linejoin']}"` : '';
            
            return `<path d="${pathData.d}" fill="${fill}" stroke="${stroke}"${strokeWidth}${strokeLinecap}${strokeLinejoin}${opacity}/>`;
        }).join('');

        const animateClass = iconData.animate?.rotate ? ' ucm-icon-rotate' : '';
        const refreshClass = iconName === 'refresh' ? ' ucm-icon-refresh' : '';
        
        // Ensure refresh icon NEVER gets the generic rotate class
        const finalAnimateClass = (iconName === 'refresh') ? '' : animateClass;
        
        const svg = `<svg class="ucm-icon ${className}${finalAnimateClass}${refreshClass}" width="${size}" height="${size}" viewBox="${iconData.viewBox}" xmlns="http://www.w3.org/2000/svg">${paths}</svg>`;
        
        // Cache the result
        this.svgCache.set(cacheKey, svg);
        
        return svg;
    }

    /**
     * Replace FontAwesome icons with dynamic SVG icons
     */
    replaceFontAwesomeIcons() {
        const iconMap = {
            'fa-gauge-high': 'dashboard',
            'fa-lock': 'certificate-authority',
            'fa-certificate': 'certificate',
            'fa-file-certificate': 'certificate',
            'fa-file-binary': 'certificate',
            'fa-truck': 'scep',
            'fa-server': 'server',
            'fa-network-wired': 'scep',
            'fa-users': 'users',
            'fa-user-group': 'users',
            'fa-gear': 'settings',
            'fa-cog': 'settings',
            'fa-user': 'user',
            'fa-user-circle': 'user',
            'fa-user-gear': 'settings',
            'fa-user-check': 'user-check',
            'fa-sync': 'refresh',
            'fa-refresh': 'refresh',
            'fa-palette': 'theme-palette',
            'fa-moon': 'moon',
            'fa-sun': 'sun',
            'fa-right-from-bracket': 'logout',
            'fa-sign-out': 'logout',
            'fa-check-circle': 'check-circle',
            'fa-check': 'check',
            'fa-exclamation-triangle': 'warning-triangle',
            'fa-exclamation-circle': 'exclamation-circle',
            'fa-warning': 'warning-triangle',
            'fa-chevron-down': 'chevron-down',
            'fa-trash': 'trash',
            'fa-ban': 'ban',
            'fa-download': 'download',
            'fa-plus': 'plus',
            'fa-plus-circle': 'plus',
            'fa-save': 'save',
            'fa-upload': 'upload',
            'fa-plug': 'plug',
            'fa-file-import': 'file-import',
            'fa-file-signature': 'file-signature',
            'fa-arrow-left': 'arrow-left',
            'fa-arrow-right': 'arrow-right',
            'fa-times': 'times',
            'fa-info-circle': 'info-circle',
            'fa-key': 'key',
            'fa-link': 'link',
            'fa-archive': 'archive',
            'fa-fingerprint': 'fingerprint',
            'fa-globe': 'globe',
            'fa-clock': 'clock',
            'fa-crown': 'crown',
            'fa-eye': 'eye',
            'fa-eye-slash': 'eye-slash',
            'fa-spinner': 'spinner',
            'fa-spin': 'spinner',
            'fa-file-contract': 'crl',
            'fa-circle-check': 'ocsp',
            'fa-check-double': 'ocsp',
            'fa-bell': 'bell',
            'fa-envelope': 'envelope',
            'fa-mail': 'envelope',
            'fa-shield-alt': 'shield-check',
            'fa-book-open': 'book-open',
            'fa-chart-bar': 'chart-bar',
            'fa-inbox': 'inbox',
            'fa-play': 'play',
            'fa-circle': 'circle'
        };

        document.querySelectorAll('i.fas, i.far, i.fab').forEach(icon => {
            for (const [faClass, iconName] of Object.entries(iconMap)) {
                if (icon.classList.contains(faClass)) {
                    const fontSize = parseInt(window.getComputedStyle(icon).fontSize) || 16;
                    const size = Math.round(fontSize * 1.3); // 30% larger
                    const className = Array.from(icon.classList).filter(c => !c.startsWith('fa')).join(' ');
                    const svgHTML = this.getIcon(iconName, className, size);
                    
                    // Skip if icon not found
                    if (!svgHTML) {
                        console.warn(`Skipping replacement for ${faClass} -> ${iconName} (icon not found)`);
                        continue;
                    }
                    
                    const temp = document.createElement('div');
                    temp.innerHTML = svgHTML;
                    const svgElement = temp.firstChild;
                    
                    if (!svgElement) {
                        console.warn(`Failed to create SVG element for ${iconName}`);
                        continue;
                    }
                    
                    // Copy any inline styles
                    if (icon.style.cssText) {
                        svgElement.style.cssText = icon.style.cssText;
                    }
                    
                    icon.parentNode.replaceChild(svgElement, icon);
                    break;
                }
            }
        });
        
        // Mark body as icons loaded
        document.body.classList.add('icons-loaded');
    }

    /**
     * Update theme and regenerate gradients
     * @param {string} newTheme - New theme name (e.g., 'sentinel-dark')
     */
    updateTheme(newTheme) {
        this.currentTheme = newTheme;
        this.svgCache.clear(); // Clear cache when theme changes
        this.injectGradientDefs(); // Regenerate gradients
        console.log('🎨 Icon system updated to theme:', newTheme);
    }
}

// Global instance
window.ucmIcons = new IconSystem();

// Auto-initialize as early as possible (before DOMContentLoaded)
(async function() {
    // Initialize immediately
    await window.ucmIcons.init();
    
    // Replace icons when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            window.ucmIcons.replaceFontAwesomeIcons();
        });
    } else {
        window.ucmIcons.replaceFontAwesomeIcons();
    }
})();

// CSS for icon animations and hiding FontAwesome during replacement
const style = document.createElement('style');
style.textContent = `
/* Hide FontAwesome icons initially to prevent flash, except in buttons */
i.fas:not(.btn i.fas):not(.btn-primary i.fas):not(.btn-secondary i.fas):not(.btn-danger i.fas):not(.btn-success i.fas), 
i.far:not(.btn i.far):not(.btn-primary i.far):not(.btn-secondary i.far):not(.btn-danger i.far):not(.btn-success i.far), 
i.fab:not(.btn i.fab):not(.btn-primary i.fab):not(.btn-secondary i.fab):not(.btn-danger i.fab):not(.btn-success i.fab) {
    opacity: 0;
    transition: opacity 0.001s;
}

/* Icons in buttons are always visible */
.btn i.fas,
.btn i.far,
.btn i.fab,
.btn-primary i.fas,
.btn-secondary i.fas,
.btn-danger i.fas,
.btn-success i.fas {
    opacity: 1 !important;
}

/* Show them after a brief moment if not replaced (fallback) */
body.icons-loaded i.fas,
body.icons-loaded i.far,
body.icons-loaded i.fab {
    opacity: 1;
}

.ucm-icon {
    display: inline-block;
    vertical-align: middle;
    flex-shrink: 0;
    opacity: 1 !important;
}

.ucm-icon-rotate {
    animation: ucm-rotate 12s linear infinite;
    transform-origin: center;
}

.btn:hover .ucm-icon-rotate,
.ucm-icon-rotate:hover {
    animation-duration: 1s;
}

@keyframes ucm-rotate {
    from {
        transform: rotate(0deg);
    }
    to {
        transform: rotate(360deg);
    }
}

/* Rotate icon when button is in HTMX request state */
.htmx-request .ucm-icon,
.htmx-request.ucm-icon {
    animation: ucm-rotate 1s linear infinite;
    transform-origin: center;
}

/* Specific handling for refresh icon to prevent unwanted rotation */
.ucm-icon-refresh,
.ucm-icon:has(use[href="#icon-refresh"]) {
    animation: none !important;
    transform: none !important;
}

.htmx-request .ucm-icon-refresh,
.htmx-request.ucm-icon-refresh,
.htmx-request .ucm-icon:has(use[href="#icon-refresh"]),
.htmx-request.ucm-icon:has(use[href="#icon-refresh"]) {
    animation: ucm-rotate 1s linear infinite !important;
}

/* Ensure icons align properly */
.btn .ucm-icon,
.sidebar-link .ucm-icon {
    margin-right: 0;
}

/* Add gradient effect to FontAwesome icons */
i.fas, i.far, i.fab {
    background: linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

/* Button icons with specific colors */
.btn-success i.fas,
.btn-success i.far {
    background: linear-gradient(135deg, var(--status-success) 0%, #059669 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.btn-danger i.fas,
.btn-danger i.far {
    background: linear-gradient(135deg, var(--status-danger) 0%, #dc2626 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.btn-warning i.fas,
.btn-warning i.far {
    background: linear-gradient(135deg, var(--status-warning) 0%, #f59e0b 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

/* Sidebar icons */
.sidebar-link i.fas,
.sidebar-link i.far {
    background: linear-gradient(135deg, var(--sidebar-text) 0%, var(--text-secondary) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.sidebar-link.active i.fas,
.sidebar-link.active i.far {
    background: linear-gradient(135deg, var(--primary-color) 0%, var(--primary-hover) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
`;
document.head.appendChild(style);
