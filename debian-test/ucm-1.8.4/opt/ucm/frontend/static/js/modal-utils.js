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
 */
window.openModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('hidden');
        lockBodyScroll();
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
