/**
 * Modal utilities - Lock body scroll when modal is open
 */

// Track open modals count
let openModalsCount = 0;

/**
 * Lock body scroll (call when opening modal)
 */
window.lockBodyScroll = function() {
    openModalsCount++;
    if (openModalsCount === 1) {
        document.body.classList.add('modal-open');
    }
};

/**
 * Unlock body scroll (call when closing modal)
 */
window.unlockBodyScroll = function() {
    openModalsCount = Math.max(0, openModalsCount - 1);
    if (openModalsCount === 0) {
        document.body.classList.remove('modal-open');
    }
};

/**
 * Helper to open any modal by ID
 * @param {string} modalId - ID of the modal element
 * @param {object} options - Options { preventOverlayClose: boolean }
 */
window.openModal = function(modalId, options = {}) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('hidden');
        lockBodyScroll();
        
        // Add close button if not exists
        addCloseButtonToModal(modal);
        
        // Handle overlay click behavior
        if (options.preventOverlayClose || hasFormInputs(modal)) {
            // Modal with form inputs - don't close on overlay click
            modal.removeAttribute('onclick');
        } else {
            // View-only modal - allow overlay click to close
            modal.setAttribute('onclick', `closeModal('${modalId}')`);
        }
    }
};

/**
 * Helper to close any modal by ID
 */
window.closeModal = function(modalId, resetForm = false) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('hidden');
        unlockBodyScroll();
        
        if (resetForm) {
            const form = modal.querySelector('form');
            if (form) form.reset();
        }
    }
};

/**
 * Check if modal contains form inputs (input, textarea, select)
 */
function hasFormInputs(modal) {
    return modal.querySelector('input, textarea, select') !== null;
}

/**
 * Add close button to modal header if not exists
 */
function addCloseButtonToModal(modal) {
    // Find modal content (first child that's not the overlay)
    const modalContent = modal.querySelector('[onclick*="stopPropagation"]') || 
                        modal.querySelector('.modal-content') ||
                        modal.children[0];
    
    if (!modalContent) return;
    
    // Find header
    const header = modalContent.querySelector('.modal-header, [style*="border-bottom"]');
    if (!header) return;
    
    // Check if close button already exists
    if (header.querySelector('[onclick*="closeModal"]')) return;
    
    // Add close button
    const closeBtn = document.createElement('button');
    closeBtn.onclick = function(e) {
        e.stopPropagation();
        const modalId = modal.id;
        closeModal(modalId, hasFormInputs(modal));
    };
    closeBtn.style.cssText = 'background: none; border: none; cursor: pointer; color: var(--text-secondary); padding: 0.25rem; margin-left: auto;';
    closeBtn.innerHTML = '<svg class="ucm-icon" width="20" height="20"><use href="#icon-times"/></svg>';
    
    // Insert as last child of header
    header.appendChild(closeBtn);
}

