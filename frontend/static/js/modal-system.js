/**
 * UCM Themed Modal System
 * Replaces native alert(), confirm(), prompt() with themed modals
 */

class UCMModal {
    constructor() {
        this.container = null;
        this.currentResolve = null;
        this.init();
    }

    init() {
        // Create modal container if it doesn't exist
        if (!document.getElementById('ucm-modal-container')) {
            const container = document.createElement('div');
            container.id = 'ucm-modal-container';
            document.body.appendChild(container);
            this.container = container;
        } else {
            this.container = document.getElementById('ucm-modal-container');
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Show an alert modal
     * @param {string} message - Message to display
     * @param {string} title - Modal title (default: 'Information')
     * @param {object} options - Additional options
     * @returns {Promise<void>}
     */
    alert(message, title = 'Information', options = {}) {
        return new Promise((resolve) => {
            this.currentResolve = resolve;
            
            const icon = options.icon || 'info-circle';
            const okText = options.okText || 'OK';
            
            const modalHTML = `
                <div class="ucm-modal-overlay" onclick="UCMModalInstance.closeModal(true)">
                    <div class="ucm-modal" onclick="event.stopPropagation()">
                        <div class="ucm-modal-header">
                            <div style="display: flex; align-items: center; gap: 0.75rem;">
                                <svg class="ucm-icon" width="24" height="24" style="color: var(--primary-color);"><use href="#icon-${icon}"/></svg>
                                <h2 class="ucm-modal-title">${this.escapeHtml(title)}</h2>
                            </div>
                        </div>
                        <div class="ucm-modal-body">
                            <p style="white-space: pre-wrap;">${this.escapeHtml(message)}</p>
                        </div>
                        <div class="ucm-modal-footer">
                            <button class="btn btn-primary" onclick="UCMModalInstance.closeModal(true)" autofocus>
                                ${this.escapeHtml(okText)}
                            </button>
                        </div>
                    </div>
                </div>
            `;
            
            this.container.innerHTML = modalHTML;
            this.addKeyboardListener();
            this.focusPrimaryButton();
        });
    }

    /**
     * Show a confirmation modal
     * @param {string} message - Message to display
     * @param {string} title - Modal title (default: 'Confirm')
     * @param {object} options - Additional options
     * @returns {Promise<boolean>}
     */
    confirm(message, title = 'Confirm', options = {}) {
        return new Promise((resolve) => {
            this.currentResolve = resolve;
            
            const icon = options.icon || 'warning-triangle';
            const confirmText = options.confirmText || 'Confirm';
            const cancelText = options.cancelText || 'Cancel';
            const danger = options.danger || false;
            
            const confirmBtnClass = danger ? 'btn btn-danger' : 'btn btn-primary';
            const iconColor = danger ? 'var(--status-danger)' : 'var(--status-warning)';
            
            const modalHTML = `
                <div class="ucm-modal-overlay" onclick="UCMModalInstance.closeModal(false)">
                    <div class="ucm-modal" onclick="event.stopPropagation()">
                        <div class="ucm-modal-header">
                            <div style="display: flex; align-items: center; gap: 0.75rem;">
                                <svg class="ucm-icon" width="24" height="24" style="color: ${iconColor};"><use href="#icon-${icon}"/></svg>
                                <h2 class="ucm-modal-title">${this.escapeHtml(title)}</h2>
                            </div>
                        </div>
                        <div class="ucm-modal-body">
                            <p style="white-space: pre-wrap;">${this.escapeHtml(message)}</p>
                        </div>
                        <div class="ucm-modal-footer">
                            <button class="btn btn-secondary" onclick="UCMModalInstance.closeModal(false)">
                                ${this.escapeHtml(cancelText)}
                            </button>
                            <button class="${confirmBtnClass}" onclick="UCMModalInstance.closeModal(true)" autofocus>
                                ${this.escapeHtml(confirmText)}
                            </button>
                        </div>
                    </div>
                </div>
            `;
            
            this.container.innerHTML = modalHTML;
            this.addKeyboardListener();
            this.focusPrimaryButton();
        });
    }

    /**
     * Close the modal and resolve the promise
     * @param {any} value - Value to resolve with
     */
    closeModal(value) {
        // Add fade-out animation
        const overlay = this.container.querySelector('.ucm-modal-overlay');
        if (overlay) {
            overlay.style.animation = 'ucm-modal-fade-out 0.2s ease-out';
            const modal = overlay.querySelector('.ucm-modal');
            if (modal) {
                modal.style.animation = 'ucm-modal-slide-out 0.2s ease-out';
            }
            
            setTimeout(() => {
                this.container.innerHTML = '';
                if (this.currentResolve) {
                    this.currentResolve(value);
                    this.currentResolve = null;
                }
                this.removeKeyboardListener();
            }, 200);
        } else {
            this.container.innerHTML = '';
            if (this.currentResolve) {
                this.currentResolve(value);
                this.currentResolve = null;
            }
            this.removeKeyboardListener();
        }
    }

    addKeyboardListener() {
        document.addEventListener('keydown', this.handleKeydown);
    }

    removeKeyboardListener() {
        document.removeEventListener('keydown', this.handleKeydown);
    }

    handleKeydown = (e) => {
        if (e.key === 'Escape') {
            e.preventDefault();
            this.closeModal(false);
        }
    }

    focusPrimaryButton() {
        setTimeout(() => {
            const primaryBtn = this.container.querySelector('button[autofocus]');
            if (primaryBtn) {
                primaryBtn.focus();
            }
        }, 100);
    }
}

// Create global instance
const UCMModalInstance = new UCMModal();

// Export global functions for easy usage
function ucmAlert(message, title, options) {
    return UCMModalInstance.alert(message, title, options);
}

function ucmConfirm(message, title, options) {
    return UCMModalInstance.confirm(message, title, options);
}

// Log initialization
console.log('✅ UCM Modal System initialized');
