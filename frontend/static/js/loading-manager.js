/**
 * UCM Loading Manager - Global spinner and loading state management
 * Provides consistent loading indicators across the application
 */

(function() {
    'use strict';

    /**
     * Show countdown and redirect after UCM restart
     * @param {number} seconds - Seconds to wait before redirect
     * @param {string} redirectUrl - URL to redirect to (default: /login)
     */
    window.showRestartCountdown = function(seconds = 5, redirectUrl = '/login') {
        // Close any open modals
        const modalContainer = document.getElementById('ucm-modal-container');
        if (modalContainer) {
            modalContainer.innerHTML = '';
        }
        
        // Show global loader with countdown
        const loader = document.getElementById('global-loader');
        if (!loader) return;
        
        loader.style.display = 'flex';
        
        const messageEl = loader.querySelector('div > div:last-child');
        if (!messageEl) return;
        
        let remaining = seconds;
        
        const updateMessage = () => {
            messageEl.innerHTML = `
                <div style="font-weight: 600; font-size: 1.125rem; margin-bottom: 0.5rem;">
                    UCM is restarting...
                </div>
                <div style="font-size: 0.875rem; color: var(--text-secondary);">
                    Redirecting to login in <strong style="color: var(--primary-color);">${remaining}</strong> second${remaining !== 1 ? 's' : ''}
                </div>
            `;
        };
        
        updateMessage();
        
        const interval = setInterval(() => {
            remaining--;
            if (remaining <= 0) {
                clearInterval(interval);
                messageEl.innerHTML = `
                    <div style="font-weight: 600; font-size: 1.125rem;">
                        Redirecting now...
                    </div>
                `;
                setTimeout(() => {
                    window.location.href = redirectUrl;
                }, 500);
            } else {
                updateMessage();
            }
        }, 1000);
    };

    /**
     * Show spinner inside a button (disables button)
     * @param {HTMLElement|string} buttonElement - Button element or selector
     * @param {string} loadingText - Optional text to show while loading (default: keeps original text)
     */
    window.showButtonSpinner = function(buttonElement, loadingText) {
        const button = typeof buttonElement === 'string' 
            ? document.querySelector(buttonElement) 
            : buttonElement;
        
        if (!button) return;

        // Store original content and state
        if (!button.dataset.originalContent) {
            button.dataset.originalContent = button.innerHTML;
            button.dataset.originalDisabled = button.disabled;
        }

        // Create spinner
        const spinner = document.createElement('span');
        spinner.className = 'spinner';
        spinner.style.cssText = 'margin-right: 0.5rem; width: 14px; height: 14px; border-width: 2px; vertical-align: middle;';

        // Set button content with spinner
        const text = loadingText || button.textContent.trim();
        button.innerHTML = '';
        button.appendChild(spinner);
        button.appendChild(document.createTextNode(' ' + text));
        
        // Disable button
        button.disabled = true;
        button.style.cursor = 'not-allowed';
        button.style.opacity = '0.7';
    };

    /**
     * Hide spinner and restore button state
     * @param {HTMLElement|string} buttonElement - Button element or selector
     */
    window.hideButtonSpinner = function(buttonElement) {
        const button = typeof buttonElement === 'string' 
            ? document.querySelector(buttonElement) 
            : buttonElement;
        
        if (!button || !button.dataset.originalContent) return;

        // Restore original content
        button.innerHTML = button.dataset.originalContent;
        
        // Restore disabled state
        button.disabled = button.dataset.originalDisabled === 'true';
        button.style.cursor = '';
        button.style.opacity = '';
        
        // Clean up data attributes
        delete button.dataset.originalContent;
        delete button.dataset.originalDisabled;
    };

    /**
     * Show global full-screen loading overlay
     * @param {string} message - Optional loading message
     * @param {number} delay - Optional delay in ms before showing (default: 250ms)
     */
    let globalLoaderTimeout = null;

    window.showGlobalLoader = function(message = 'Loading...', delay = 250) {
        const loader = document.getElementById('global-loader');
        if (loader) {
            const messageEl = loader.querySelector('div > div:last-child');
            if (messageEl) messageEl.textContent = message;
            
            // Clear any existing timeout
            if (globalLoaderTimeout) {
                clearTimeout(globalLoaderTimeout);
            }
            
            // Set new timeout to show loader
            globalLoaderTimeout = setTimeout(() => {
                loader.style.display = 'flex';
                // Add a small fade-in animation
                loader.style.opacity = '0';
                loader.style.transition = 'opacity 0.2s ease';
                requestAnimationFrame(() => {
                    loader.style.opacity = '1';
                });
            }, delay);
        }
    };

    /**
     * Hide global loading overlay
     */
    window.hideGlobalLoader = function() {
        // Clear any pending timeout (so it doesn't show up if task finished quickly)
        if (globalLoaderTimeout) {
            clearTimeout(globalLoaderTimeout);
            globalLoaderTimeout = null;
        }

        const loader = document.getElementById('global-loader');
        if (loader) {
            loader.style.display = 'none';
            loader.style.opacity = '0'; // Reset opacity for next time
        }
    };

    /**
     * Show inline spinner in a container
     * @param {HTMLElement|string} containerElement - Container element or selector
     * @param {string} message - Optional message to show
     * @returns {HTMLElement} The created spinner container
     */
    window.showInlineSpinner = function(containerElement, message = '') {
        const container = typeof containerElement === 'string' 
            ? document.querySelector(containerElement) 
            : containerElement;
        
        if (!container) return null;

        const spinnerContainer = document.createElement('div');
        spinnerContainer.className = 'inline-spinner-container';
        spinnerContainer.style.cssText = 'text-align: center; padding: 2rem;';
        
        const spinner = document.createElement('div');
        spinner.className = 'spinner';
        spinner.style.cssText = 'margin: 0 auto;';
        
        spinnerContainer.appendChild(spinner);
        
        if (message) {
            const text = document.createElement('p');
            text.textContent = message;
            text.style.cssText = 'margin-top: 0.75rem; color: var(--text-secondary); font-size: 0.875rem;';
            spinnerContainer.appendChild(text);
        }
        
        container.innerHTML = '';
        container.appendChild(spinnerContainer);
        
        return spinnerContainer;
    };

    /**
     * Wrap an async function with automatic button spinner
     * @param {HTMLElement} button - Button element
     * @param {Function} asyncFunction - Async function to execute
     * @param {string} loadingText - Optional loading text
     */
    window.withButtonSpinner = async function(button, asyncFunction, loadingText) {
        showButtonSpinner(button, loadingText);
        try {
            return await asyncFunction();
        } finally {
            hideButtonSpinner(button);
        }
    };

    /**
     * Create a spinner element
     * @param {string} size - Size: 'sm', 'md', 'lg' (default: 'md')
     * @returns {HTMLElement} Spinner element
     */
    window.createSpinner = function(size = 'md') {
        const spinner = document.createElement('div');
        spinner.className = 'spinner';
        
        const sizes = {
            'sm': 'width: 14px; height: 14px; border-width: 2px;',
            'md': 'width: 20px; height: 20px; border-width: 2px;',
            'lg': 'width: 40px; height: 40px; border-width: 3px;'
        };
        
        spinner.style.cssText = sizes[size] || sizes['md'];
        return spinner;
    };

    // Auto-add spinner to forms with data-loading attribute
    document.addEventListener('submit', function(e) {
        const form = e.target;
        if (form.dataset.loading !== undefined) {
            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            if (submitBtn) {
                showButtonSpinner(submitBtn);
            }
        }
    });

    // Intercept fetch calls to show global loader for long requests (optional)
    if (window.UCM_AUTO_LOADER_ENABLED) {
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            const timeout = setTimeout(() => showGlobalLoader(), 500); // Show after 500ms
            
            return originalFetch.apply(this, args)
                .finally(() => {
                    clearTimeout(timeout);
                    hideGlobalLoader();
                });
        };
    }

    console.log('✓ UCM Loading Manager initialized');
})();
