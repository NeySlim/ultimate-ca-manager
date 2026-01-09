/**
 * UCM Global Functions
 * Shared JavaScript functions used across all pages
 * Version: 1.0.0
 */

// ============================================================================
// CERTIFICATE FUNCTIONS
// ============================================================================

function openCreateCertModal() {
    openModal('createCertModal');
}

function closeCertModal() {
    closeModal('createCertModal');
}

function updateCertTypeHints(certType) {
    const hints = {
        'server_cert': 'For web servers, VPNs, and other services',
        'client_cert': 'For user authentication (VPN, email, etc.)',
        'combined_cert': 'Can be used for both server and client authentication',
        'ca_cert': 'For creating an intermediate Certificate Authority'
    };
    const hintEl = document.getElementById('cert-type-hint');
    if (hintEl) {
        hintEl.textContent = hints[certType] || '';
    }
}

function openCSRModal() {
    openModal('csrModal');
}

function closeCSRModal() {
    closeModal('csrModal');
}

function handleCertCreateResponse(event) {
    console.log('Form submitted, success:', event.detail.successful, 'target:', event.detail.target);
    if (event.detail.successful && event.detail.target && event.detail.target.tagName === 'FORM') {
        closeCertModal();
        htmx.trigger('body', 'refreshCerts');
        showToast('Certificate created', 'success');
    }
}

function handleCSRResponse(event) {
    if (event.detail.successful && event.detail.target && event.detail.target.tagName === 'FORM') {
        closeCSRModal();
        htmx.trigger('body', 'refreshCerts');
        showToast('CSR generated', 'success');
    }
}

// Auto-open create modal if hash is #create
function checkCreateHash() {
    if (window.location.hash === '#create') {
        setTimeout(() => {
            openCreateCertModal();
            // Remove hash from URL after opening modal
            history.replaceState(null, null, window.location.pathname);
        }, 100);
    }
}

// ============================================================================
// CA FUNCTIONS
// ============================================================================

function openCreateCAModal() {
    openModal('createCAModal');
}

function closeCreateCAModal() {
    closeModal('createCAModal', true);
}

function openImportCAModal() {
    openModal('importCAModal');
}

function closeImportCAModal() {
    closeModal('importCAModal', true);
}

function handleCACreateResponse(event) {
    if (event.detail.successful) {
        closeCreateCAModal();
        htmx.trigger('body', 'refreshCAs');
        showNotification('CA created successfully', 'success');
    } else {
        showNotification('Error creating CA: ' + event.detail.xhr.responseText, 'error');
    }
}

function handleCAImportResponse(event) {
    if (event.detail.successful) {
        closeImportCAModal();
        htmx.trigger('body', 'refreshCAs');
        showNotification('CA imported successfully', 'success');
    } else {
        showNotification('Error importing CA: ' + event.detail.xhr.responseText, 'error');
    }
}

function deleteCA(refid, name) {
    // Get token from session
    const tokenMeta = document.querySelector('meta[name="access-token"]');
    const token = tokenMeta ? tokenMeta.content : '';
    
    if (typeof ucmConfirm !== 'undefined') {
        ucmConfirm(
            `Delete CA "${name}"?\n\nThis cannot be undone! All certificates signed by this CA will be affected.`,
            'Delete CA',
            { danger: true, confirmText: 'Delete', icon: 'trash' }
        ).then(confirmed => {
            if (!confirmed) return;
            performCADelete(refid, token);
        });
    } else {
        if (confirm(`Delete CA "${name}"? This cannot be undone!`)) {
            performCADelete(refid, token);
        }
    }
}

function performCADelete(refid, token) {
    fetch(`/api/v1/ca/${refid}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(response => {
        if (response.ok) {
            showToast('CA deleted successfully', 'success');
            htmx.trigger('body', 'refreshCAs');
        } else {
            return response.json().then(data => {
                throw new Error(data.error || 'Delete failed');
            });
        }
    })
    .catch(e => {
        showToast('Error: ' + e.message, 'error');
    });
}

function deleteCert(refid, name) {
    // Get token from session
    const tokenMeta = document.querySelector('meta[name="access-token"]');
    const token = tokenMeta ? tokenMeta.content : '';
    
    if (typeof ucmConfirm !== 'undefined') {
        ucmConfirm(
            `Delete certificate "${name}"?\n\nThis action cannot be undone.`,
            'Delete Certificate',
            { danger: true, confirmText: 'Delete', icon: 'trash' }
        ).then(confirmed => {
            if (!confirmed) return;
            performCertDelete(refid, token);
        });
    } else {
        if (confirm(`Delete certificate "${name}"?`)) {
            performCertDelete(refid, token);
        }
    }
}

function performCertDelete(refid, token) {
    fetch(`/api/v1/certificates/by-refid/${refid}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(response => {
        if (response.ok) {
            showToast('Certificate deleted successfully', 'success');
            htmx.trigger('body', 'refreshCerts');
        } else {
            return response.json().then(data => {
                throw new Error(data.error || 'Delete failed');
            });
        }
    })
    .catch(e => {
        showToast('Error: ' + e.message, 'error');
    });
}

// ============================================================================
// PKCS#12 FUNCTIONS
// ============================================================================

function showPKCS12Modal(id, type) {
    window.pkcs12Params = { id, type };
    openModal('pkcs12PasswordModal');
    const pwdEl = document.getElementById('pkcs12Password');
    const confirmEl = document.getElementById('pkcs12PasswordConfirm');
    if (pwdEl) pwdEl.value = '';
    if (confirmEl) confirmEl.value = '';
}

// Alias for table usage
function showPKCS12ModalTable(id, type) {
    showPKCS12Modal(id, type);
}

function closePKCS12Modal() {
    closeModal('pkcs12PasswordModal');
    window.pkcs12Params = {};
}

function downloadPKCS12WithPassword() {
    const password = document.getElementById('pkcs12Password').value;
    const confirm = document.getElementById('pkcs12PasswordConfirm').value;
    
    if (!password || password.length < 4) {
        ucmAlert('Password must be at least 4 characters', 'Error');
        return;
    }
    
    if (password !== confirm) {
        ucmAlert('Passwords do not match', 'Error');
        return;
    }
    
    const { id, type } = window.pkcs12Params;
    
    if (!id || !type) {
        ucmAlert('Invalid PKCS#12 parameters', 'Error');
        return;
    }
    
    // Build download URL
    const url = `/api/v1/${type === 'ca' ? 'ca' : 'certificates'}/${id}/export/pkcs12?password=${encodeURIComponent(password)}`;
    
    // Download file
    const link = document.createElement('a');
    link.href = url;
    link.download = `${type}-${id}.p12`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    closePKCS12Modal();
    showToast('PKCS#12 export started', 'success');
}

// ============================================================================
// NOTIFICATION FUNCTIONS
// ============================================================================

function showNotification(message, type) {
    // Use ucmAlert from modal-system.js if available
    if (typeof ucmAlert !== 'undefined') {
        ucmAlert(message, type === 'error' ? 'Error' : 'Notification');
    } else {
        // Fallback to toast
        showToast(message, type === 'error' ? 'danger' : 'success');
    }
}

function showToast(message, type = 'success') {
    console.log('🔔 showToast called:', message, 'type:', type);
    
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        top: 1rem;
        right: 1rem;
        padding: 1rem 1.5rem;
        border-radius: 0.5rem;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        z-index: 9999;
        color: white;
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 0.75rem;
        min-width: 250px;
        animation: slideIn 0.3s ease-out;
    `;
    
    // Set background color based on type
    const colors = {
        'success': '#10b981',
        'error': '#ef4444',
        'danger': '#ef4444',
        'warning': '#f59e0b',
        'info': '#3b82f6'
    };
    toast.style.backgroundColor = colors[type] || colors.success;
    
    // Set icon based on type
    const icons = {
        'success': 'fa-check-circle',
        'error': 'fa-exclamation-circle',
        'danger': 'fa-exclamation-circle',
        'warning': 'fa-exclamation-triangle',
        'info': 'fa-info-circle'
    };
    const icon = icons[type] || icons.success;
    
    toast.innerHTML = `
        <i class="fas ${icon}"></i>
        <span>${message}</span>
    `;
    
    // Add animation
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        @keyframes slideOut {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(100%);
                opacity: 0;
            }
        }
    `;
    if (!document.querySelector('style[data-toast-animation]')) {
        style.setAttribute('data-toast-animation', 'true');
        document.head.appendChild(style);
    }
    
    document.body.appendChild(toast);
    
    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function refreshPage() {
    window.location.reload();
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard', 'success');
    }).catch(err => {
        console.error('Failed to copy:', err);
        showToast('Failed to copy to clipboard', 'error');
    });
}

// ============================================================================
// INITIALIZATION
// ============================================================================

// Auto-run on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ UCM Global Functions loaded');
    
    // Check for hash-based actions
    checkCreateHash();
});

// Re-run after HTMX swaps (for SPA navigation)
document.addEventListener('htmx:afterSwap', function() {
    checkCreateHash();
});

console.log('📦 UCM Global Functions module loaded');
