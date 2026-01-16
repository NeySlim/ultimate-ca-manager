/**
 * UCM Global Functions
 * Shared JavaScript functions used across all pages
 * Version: 1.0.0
 */

// ============================================================================
// UI UTILITY FUNCTIONS
// ============================================================================

/**
 * Universal Tab Switching with Inline Styles (The "Spacious" Design)
 * Handles tab switching by manipulating inline styles directly to guarantee
 * identical appearance across all pages regardless of CSS quirks.
 * 
 * @param {string} tabName - The ID suffix of the tab to show
 * @param {string} containerSelector - Selector for the tab buttons container (optional)
 */
window.ucm_switchTab = function(tabName, containerSelector = '.tabs-container') {
    // 1. Hide all tab content panels
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.style.display = 'none';
        tab.classList.remove('active');
    });

    // 2. Reset all buttons in the container to "Inactive" state (inline styles)
    const container = document.querySelector(containerSelector);
    if (container) {
        container.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.remove('active');
            btn.style.color = 'var(--text-secondary)';
            btn.style.borderBottomColor = 'transparent';
            btn.style.fontWeight = '500';
        });
    }

    // 3. Show selected content
    const selectedTab = document.getElementById('tab-' + tabName);
    if (selectedTab) {
        selectedTab.style.display = 'block';
        selectedTab.classList.add('active');
    }

    // 4. Set active button state (inline styles)
    const activeBtn = document.getElementById('btn-tab-' + tabName);
    if (activeBtn) {
        activeBtn.classList.add('active');
        activeBtn.style.color = 'var(--primary-color)';
        activeBtn.style.borderBottomColor = 'var(--primary-color)';
        activeBtn.style.fontWeight = '600';
    }

    // 5. Save preference if valid
    if (tabName) {
        // Try to guess context from URL or fallback to generic
        const context = window.location.pathname.split('/')[1] || 'general';
        localStorage.setItem(`ucm-tab-${context}`, tabName);
    }
};

// ============================================================================
// SECURITY UTILITY FUNCTIONS
// ============================================================================

/**
 * Escape HTML to prevent XSS attacks
 * Use this when inserting user-controlled data into innerHTML
 */
window.escapeHtml = function(unsafe) {
    if (unsafe === null || unsafe === undefined) return '';
    return String(unsafe)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
};

// ============================================================================
// MODAL UTILITY FUNCTIONS
// ============================================================================

function openModal(modalId) {
    console.log('Opening modal:', modalId);
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('hidden');
        console.log('Modal opened:', modalId);
    } else {
        console.error('Modal not found:', modalId);
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('hidden');
    }
}

// ============================================================================
// CERTIFICATE FUNCTIONS
// ============================================================================

function openCreateCertModal() {
    console.log('Opening create cert modal');
    openModal('createCertModal');
    // Load CA options after modal is visible
    setTimeout(() => {
        const modal = document.getElementById('createCertModal');
        if (modal) {
            const form = modal.querySelector('form');
            if (form) {
                form.reset();
                console.log('Form reset after modal open');
            }
            // Load CA options directly via HTMX ajax
            const caSelect = document.getElementById('ca-select');
            if (caSelect && typeof htmx !== 'undefined') {
                htmx.ajax('GET', '/api/ui/ca/options', {
                    target: '#ca-select',
                    swap: 'innerHTML'
                });
                console.log('CA options load triggered via htmx.ajax');
            }
            // Pre-fill OCSP URI with current server URL
            const ocspInput = document.getElementById('ocsp-uri-input');
            if (ocspInput && !ocspInput.value) {
                const baseUrl = window.location.protocol + '//' + window.location.host;
                ocspInput.value = baseUrl + '/ocsp';
                console.log('OCSP URI pre-filled:', ocspInput.value);
            }
        }
    }, 100);
    console.log('Modal opened');
}

function closeCertModal() {
    closeModal('createCertModal');
}

function openAddUserModal() {
    openModal('addUserModal');
}

function closeAddUserModal() {
    closeModal('addUserModal');
}

function openChangePasswordModal(userId, username) {
    document.getElementById('change-password-user-id').value = userId;
    document.getElementById('change-password-username').textContent = `User: ${username}`;
    openModal('changePasswordModal');
}

function closeChangePasswordModal() {
    closeModal('changePasswordModal');
}

function openChangeRoleModal(userId, username, currentRole) {
    document.getElementById('change-role-user-id').value = userId;
    document.getElementById('change-role-username').textContent = `User: ${username} (Current: ${currentRole})`;
    
    // Populate role options
    const roles = [
        { value: 'viewer', label: 'Viewer', icon: 'eye', color: 'var(--info-color)', desc: 'Read-only access to certificates and CAs' },
        { value: 'operator', label: 'Operator', icon: 'cog', color: 'var(--warning-color)', desc: 'Can create and manage certificates' },
        { value: 'admin', label: 'Administrator', icon: 'shield-alt', color: 'var(--danger-color)', desc: 'Full access including user management' }
    ];
    
    const container = document.getElementById('role-options');
    container.innerHTML = roles.map(role => `
        <label class="role-option" data-role="${role.value}">
            <input type="radio" name="role" value="${role.value}" required ${role.value === currentRole ? 'checked' : ''}>
            <div>
                <div style="font-weight: 600; color: var(--text-primary);">
                    <i class="fas fa-${role.icon}" style="margin-right: 0.5rem; color: ${role.color};"></i> ${role.label}
                </div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">${role.desc}</div>
            </div>
        </label>
    `).join('');
    
    // Add event listeners for role selection styling
    container.querySelectorAll('input[type="radio"]').forEach(radio => {
        radio.addEventListener('change', () => {
            container.querySelectorAll('.role-option').forEach(label => {
                const input = label.querySelector('input');
                const roleData = roles.find(r => r.value === label.dataset.role);
                if (input.checked) {
                    label.style.cssText = `border-color: ${roleData.color}; background: var(--bg-secondary);`;
                } else {
                    label.style.cssText = '';
                }
            });
        });
        // Trigger initial state
        if (radio.checked) radio.dispatchEvent(new Event('change'));
    });
    
    openModal('changeRoleModal');
}

function closeChangeRoleModal() {
    closeModal('changeRoleModal');
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
    // Get token from global variable
    if (typeof ucmConfirm !== 'undefined') {
        ucmConfirm(
            `Delete CA "${name}"?\n\nThis cannot be undone! All certificates signed by this CA will be affected.`,
            'Delete CA',
            { danger: true, confirmText: 'Delete', icon: 'trash' }
        ).then(confirmed => {
            if (!confirmed) return;
            performCADelete(refid);
        });
    } else {
        if (confirm(`Delete CA "${name}"? This cannot be undone!`)) {
            performCADelete(refid);
        }
    }
}

function performCADelete(refid) {
    fetch(`/api/v1/ca/${refid}`, {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }
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
    if (typeof ucmConfirm !== 'undefined') {
        ucmConfirm(
            `Delete certificate "${name}"?\n\nThis action cannot be undone.`,
            'Delete Certificate',
            { danger: true, confirmText: 'Delete', icon: 'trash' }
        ).then(confirmed => {
            if (!confirmed) return;
            performCertDelete(refid);
        });
    } else {
        if (confirm(`Delete certificate "${name}"?`)) {
            performCertDelete(refid);
        }
    }
}

function performCertDelete(refid) {
    fetch(`/api/v1/certificates/by-refid/${refid}`, {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }
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

function revokeCert(refid, name) {
    // Get token from global variable
    if (typeof ucmConfirm !== 'undefined') {
        ucmConfirm(
            `Revoke certificate "${name}"?\n\nThis cannot be undone. The certificate will be marked as revoked.`,
            'Revoke Certificate',
            { danger: true, confirmText: 'Revoke', icon: 'warning-triangle' }
        ).then(confirmed => {
            if (!confirmed) return;
            performCertRevoke(refid);
        });
    } else {
        if (confirm(`Revoke certificate "${name}"?`)) {
            performCertRevoke(refid);
        }
    }
}

function performCertRevoke(refid) {
    fetch(`/api/v1/certificates/by-refid/${refid}/revoke`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ reason: 'unspecified' })
    })
    .then(response => {
        if (response.ok) {
            showToast('Certificate revoked successfully', 'success');
            htmx.trigger('body', 'refreshCerts');
        } else {
            return response.json().then(data => {
                throw new Error(data.error || 'Revoke failed');
            });
        }
    })
    .catch(e => {
        showToast('Error: ' + e.message, 'error');
    });
}

// ============================================================================
// EXPORT FUNCTIONS
// ============================================================================
/**
 * Global export function with JWT authentication
 * Uses window.UCM_TOKEN which should be set by each page template
 */
if (typeof window.exportWithToken === 'undefined') {
    window.exportWithToken = function(url) {
        const token = window.UCM_TOKEN;
        if (!token) {
            console.error('UCM_TOKEN not set! Cannot authenticate export.');
            showToast('Authentication error - please refresh the page', 'error');
            return;
        }
        
        showToast('Preparing download...', 'info');
        
        fetch(url, {
            headers: { 'Authorization': 'Bearer ' + token }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            // Extract filename from Content-Disposition header
            let filename = '';
            const disposition = response.headers.get('Content-Disposition');
            if (disposition && disposition.includes('filename=')) {
                const matches = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                if (matches && matches[1]) {
                    filename = matches[1].replace(/['"]/g, '');
                }
            }
            
            // Fallback to URL-based filename
            if (!filename) {
                const urlParts = url.split('/');
                filename = urlParts[urlParts.length - 1].split('?')[0] || 'download';
            }
            
            return response.blob().then(blob => ({blob, filename}));
        })
        .then(({blob, filename}) => {
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(downloadUrl);
            showToast('Download started: ' + filename, 'success');
        })
        .catch(error => {
            console.error('Export failed:', error);
            showToast('Export failed: ' + error.message, 'error');
        });
    };
}

// ============================================================================
// EXPORT FUNCTIONS
// ============================================================================
// NOTE: Export functions (exportCertSimple, exportCertWithChain, exportCASimple, etc.)
// are defined in template inline scripts with proper JWT token injection.
// DO NOT define them here as globals - they would override the authenticated versions.
// Each page template (ca/list.html, certs/list.html, ca/detail.html, certs/detail.html, dashboard.html)
// defines its own exportWithToken() function with the JWT token from the session.

// ============================================================================
// CRL FUNCTIONS
// ============================================================================

function generateCRL(caId, caName) {
    if (typeof ucmConfirm !== 'undefined') {
        ucmConfirm(
            `Generate new CRL for ${caName}?`,
            'Generate CRL',
            { confirmText: 'Generate', icon: 'refresh' }
        ).then(confirmed => {
            if (!confirmed) return;
            performGenerateCRL(caId);
        });
    } else {
        if (confirm(`Generate new CRL for ${caName}?`)) {
            performGenerateCRL(caId);
        }
    }
}

function performGenerateCRL(caId) {
    fetch(`/api/v1/crl/${caId}/generate`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            if (typeof ucmAlert !== 'undefined') {
                ucmAlert(`Error: ${data.error}`, 'Error');
            } else {
                showToast(`Error: ${data.error}`, 'error');
            }
        } else {
            const message = `CRL #${data.crl.crl_number} generated successfully`;
            if (typeof ucmAlert !== 'undefined') {
                ucmAlert(message, 'Success').then(() => {
                    if (typeof refreshCRLs !== 'undefined') refreshCRLs();
                });
            } else {
                showToast(message, 'success');
                if (typeof refreshCRLs !== 'undefined') refreshCRLs();
            }
        }
    })
    .catch(error => {
        if (typeof ucmAlert !== 'undefined') {
            ucmAlert(`Failed to generate CRL: ${error.message}`, 'Error');
        } else {
            showToast(`Failed to generate CRL: ${error.message}`, 'error');
        }
    });
}

function downloadCRL(caId, format) {
    const url = `/api/v1/crl/${caId}/download?format=${format}`;
    exportWithToken(url);
}

function viewCRLInfo(caRefid) {
    window.location.href = `/crl/info/${caRefid}`;
}

function refreshCRLs() {
    // Trigger HTMX refresh if available
    if (typeof htmx !== 'undefined') {
        htmx.trigger('body', 'refreshCRLs');
    } else {
        location.reload();
    }
}

// ============================================================================
// SCEP FUNCTIONS
// ============================================================================

function approveSCEP(txid) {
    fetch('/scep/requests/' + txid + '/approve', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(r => r.json())
    .then(() => {
        showToast('Request approved', 'success');
        if (typeof htmx !== 'undefined') {
            htmx.trigger('body', 'refreshSCEP');
        }
    })
    .catch(e => showToast('Error: ' + e, 'error'));
}

function rejectSCEP(txid) {
    fetch('/scep/requests/' + txid + '/reject', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Rejected by administrator' })
    })
    .then(r => r.json())
    .then(() => {
        showToast('Request rejected', 'success');
        if (typeof htmx !== 'undefined') {
            htmx.trigger('body', 'refreshSCEP');
        }
    })
    .catch(e => showToast('Error: ' + e, 'error'));
}

// ============================================================================
// TABLE SORTING & FILTERING
// ============================================================================

// Initialize sort direction trackers
if (typeof window.sortDirectionCA === 'undefined') {
    window.sortDirectionCA = {};
}
if (typeof window.sortDirectionCert === 'undefined') {
    window.sortDirectionCert = {};
}

if (typeof window.sortDirectionCA === 'undefined') {
    window.sortDirectionCA = {};
}

function sortTable(columnIndex) {
    const table = document.getElementById('ca-table');
    if (!table) return;
    
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    const currentDirection = window.sortDirectionCA[columnIndex] || 'asc';
    const newDirection = currentDirection === 'asc' ? 'desc' : 'asc';
    window.sortDirectionCA[columnIndex] = newDirection;
    
    rows.sort((a, b) => {
        let aValue = a.cells[columnIndex].textContent.trim();
        let bValue = b.cells[columnIndex].textContent.trim();
        
        // Handle numeric values for usage column (column 3)
        if (columnIndex === 3) {
            aValue = parseInt(aValue) || 0;
            bValue = parseInt(bValue) || 0;
        }
        
        if (aValue < bValue) return newDirection === 'asc' ? -1 : 1;
        if (aValue > bValue) return newDirection === 'asc' ? 1 : -1;
        return 0;
    });
    
    rows.forEach(row => tbody.appendChild(row));
}

function sortTableCert(columnIndex) {
    const table = document.getElementById('cert-table');
    if (!table) return;
    
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    const currentDirection = window.sortDirectionCert[columnIndex] || 'asc';
    const newDirection = currentDirection === 'asc' ? 'desc' : 'asc';
    window.sortDirectionCert[columnIndex] = newDirection;
    
    rows.sort((a, b) => {
        let aValue = a.cells[columnIndex].textContent.trim();
        let bValue = b.cells[columnIndex].textContent.trim();
        
        if (aValue < bValue) return newDirection === 'asc' ? -1 : 1;
        if (aValue > bValue) return newDirection === 'asc' ? 1 : -1;
        return 0;
    });
    
    rows.forEach(row => tbody.appendChild(row));
}

function sortTableCA(columnIndex) {
    const table = document.getElementById('ca-table');
    if (!table) return;
    
    const tbody = table.querySelector('tbody');
    const allRows = Array.from(tbody.querySelectorAll('tr'));
    
    // Separate ROOT CAs (parent rows) from intermediate CAs (children)
    const rootRows = allRows.filter(row => !row.classList.contains('ca-child-row'));
    const childMap = new Map(); // Map parent row to its children
    
    // Build map of children for each parent
    allRows.forEach((row, index) => {
        if (row.classList.contains('ca-child-row')) {
            // Find previous ROOT CA (parent)
            for (let i = index - 1; i >= 0; i--) {
                if (!allRows[i].classList.contains('ca-child-row')) {
                    if (!childMap.has(allRows[i])) {
                        childMap.set(allRows[i], []);
                    }
                    childMap.get(allRows[i]).push(row);
                    break;
                }
            }
        }
    });
    
    const currentDirection = window.sortDirectionCA[columnIndex] || 'asc';
    const newDirection = currentDirection === 'asc' ? 'desc' : 'asc';
    window.sortDirectionCA[columnIndex] = newDirection;
    
    // Sort only ROOT CAs
    rootRows.sort((a, b) => {
        let aValue = a.cells[columnIndex].textContent.trim();
        let bValue = b.cells[columnIndex].textContent.trim();
        
        if (aValue < bValue) return newDirection === 'asc' ? -1 : 1;
        if (aValue > bValue) return newDirection === 'asc' ? 1 : -1;
        return 0;
    });
    
    // Rebuild table: each ROOT CA followed by its children
    tbody.innerHTML = '';
    rootRows.forEach(rootRow => {
        tbody.appendChild(rootRow);
        // Append children if any
        if (childMap.has(rootRow)) {
            childMap.get(rootRow).forEach(childRow => {
                tbody.appendChild(childRow);
            });
        }
    });
}

function filterTableCA() {
    const input = document.getElementById('searchCA');
    if (!input) return;
    
    const filter = input.value.toLowerCase();
    const table = document.getElementById('ca-table');
    const tbody = table.querySelector('tbody');
    const rows = tbody.querySelectorAll('tr');
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(filter) ? '' : 'none';
    });
}

function filterTableCert() {
    const input = document.getElementById('searchCert');
    if (!input) return;
    
    const filter = input.value.toLowerCase();
    const table = document.getElementById('cert-table');
    const tbody = table.querySelector('tbody');
    const rows = tbody.querySelectorAll('tr');
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(filter) ? '' : 'none';
    });
}

// ============================================================================
// CERTIFICATE PAGINATION FUNCTIONS
// ============================================================================

if (typeof window.certCurrentPage === 'undefined') {
    window.certCurrentPage = 1;
}
if (typeof window.certPerPage === 'undefined') {
    window.certPerPage = 10;
}
if (typeof window.certTotalRows === 'undefined') {
    window.certTotalRows = 0;
}

function initCertPagination() {
    const table = document.getElementById('cert-table');
    if (!table) return;
    
    const tbody = table.querySelector('tbody');
    window.certTotalRows = tbody.querySelectorAll('tr').length;
    
    const totalEl = document.getElementById('cert-total');
    if (totalEl) totalEl.textContent = window.certTotalRows;
    updateCertPagination();
}

function updateCertPagination() {
    const perPageSelect = document.getElementById('cert-per-page');
    if (!perPageSelect) return;
    
    window.certPerPage = parseInt(perPageSelect.value);
    const totalPages = Math.ceil(window.certTotalRows / window.certPerPage);
    
    showCertPage(window.certCurrentPage, totalPages);
    renderCertPaginationButtons(totalPages);
}

function showCertPage(page, totalPages) {
    const table = document.getElementById('cert-table');
    if (!table) return;
    
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    const start = (page - 1) * window.certPerPage;
    const end = start + window.certPerPage;
    
    rows.forEach((row, index) => {
        row.style.display = (index >= start && index < end) ? '' : 'none';
    });
    
    // Update info
    const actualStart = Math.min(start + 1, window.certTotalRows);
    const actualEnd = Math.min(end, window.certTotalRows);
    
    const startEl = document.getElementById('cert-start');
    const endEl = document.getElementById('cert-end');
    if (startEl) startEl.textContent = actualStart;
    if (endEl) endEl.textContent = actualEnd;
}

function renderCertPaginationButtons(totalPages) {
    const container = document.getElementById('cert-pagination-buttons');
    if (!container) return;
    
    let html = '';
    
    // Previous button
    html += `<button class="pagination-btn" onclick="goToCertPage(${window.certCurrentPage - 1}, ${totalPages})" ${window.certCurrentPage === 1 ? 'disabled' : ''}>
        <svg class="ucm-icon" width="14" height="14"><use href="#icon-chevron-left"/></svg>
    </button>`;
    
    // Page numbers
    const maxButtons = 7;
    let startPage = Math.max(1, window.certCurrentPage - Math.floor(maxButtons / 2));
    let endPage = Math.min(totalPages, startPage + maxButtons - 1);
    
    if (endPage - startPage < maxButtons - 1) {
        startPage = Math.max(1, endPage - maxButtons + 1);
    }
    
    if (startPage > 1) {
        html += `<button class="pagination-btn" onclick="goToCertPage(1, ${totalPages})">1</button>`;
        if (startPage > 2) {
            html += `<span class="pagination-ellipsis">...</span>`;
        }
    }
    
    for (let i = startPage; i <= endPage; i++) {
        html += `<button class="pagination-btn ${i === window.certCurrentPage ? 'active' : ''}" 
                 onclick="goToCertPage(${i}, ${totalPages})">${i}</button>`;
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            html += `<span class="pagination-ellipsis">...</span>`;
        }
        html += `<button class="pagination-btn" onclick="goToCertPage(${totalPages}, ${totalPages})">${totalPages}</button>`;
    }
    
    // Next button
    html += `<button class="pagination-btn" onclick="goToCertPage(${window.certCurrentPage + 1}, ${totalPages})" ${window.certCurrentPage === totalPages ? 'disabled' : ''}>
        <svg class="ucm-icon" width="14" height="14"><use href="#icon-chevron-right"/></svg>
    </button>`;
    
    container.innerHTML = html;
}

function goToCertPage(page, totalPages) {
    if (page < 1 || page > totalPages) return;
    window.certCurrentPage = page;
    showCertPage(page, totalPages);
    renderCertPaginationButtons(totalPages);
}

// ============================================================================
// THEME SWITCHER FUNCTIONS
// ============================================================================

function toggleDropdown() {
    const dropdown = document.getElementById('themeDropdown');
    if (dropdown) {
        dropdown.classList.toggle('active');
    }
}

function closeDropdown() {
    const dropdown = document.getElementById('themeDropdown');
    if (dropdown) {
        dropdown.classList.remove('active');
    }
}

// Note: setTheme() is already defined in theme-switcher.js
// These are just helper functions for dropdowns

// ============================================================================
// IMPORT FUNCTIONS
// ============================================================================

function switchImportMethod(method) {
    // Update tab buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
        btn.style.borderBottomColor = 'transparent';
        btn.style.color = 'var(--text-secondary)';
    });
    
    const clickedBtn = event?.target?.closest('.tab-button');
    if (clickedBtn) {
        clickedBtn.classList.add('active');
        clickedBtn.style.borderBottomColor = 'var(--primary-color)';
        clickedBtn.style.color = 'var(--primary-color)';
    }
    
    // Hide all method panels
    const pasteEl = document.getElementById('paste-method');
    const uploadEl = document.getElementById('upload-method');
    const containerEl = document.getElementById('container-method');
    
    if (pasteEl) pasteEl.style.display = 'none';
    if (uploadEl) uploadEl.style.display = 'none';
    if (containerEl) containerEl.style.display = 'none';
    
    // Show selected method
    if (method === 'paste' && pasteEl) {
        pasteEl.style.display = 'grid';
    } else if (method === 'upload' && uploadEl) {
        uploadEl.style.display = 'grid';
    } else if (method === 'container' && containerEl) {
        containerEl.style.display = 'grid';
    }
}

function clearManualForm() {
    // Clear CA import form
    const caDescr = document.getElementById('ca-description');
    const caCert = document.getElementById('ca-certificate');
    const caKey = document.getElementById('ca-private-key');
    
    if (caDescr) caDescr.value = '';
    if (caCert) caCert.value = '';
    if (caKey) caKey.value = '';
    
    // Clear Certificate import form
    const certDescr = document.getElementById('cert-description');
    const certCert = document.getElementById('cert-certificate');
    const certKey = document.getElementById('cert-private-key');
    const certCA = document.getElementById('cert-ca');
    
    if (certDescr) certDescr.value = '';
    if (certCert) certCert.value = '';
    if (certKey) certKey.value = '';
    if (certCA) certCA.value = '';
    
    // Clear status messages
    const statusEl = document.getElementById('manual-import-status');
    if (statusEl) statusEl.innerHTML = '';
}

// Note: importManualCA() and importManualCertificate() are complex async functions
// that are page-specific. The generic onclick handler will call them if they exist
// in the template scope.

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            showToast('Copied to clipboard!', 'success');
        }).catch(err => {
            console.error('Failed to copy:', err);
            showToast('Failed to copy to clipboard', 'error');
        });
    } else {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            showToast('Copied to clipboard!', 'success');
        } catch (err) {
            showToast('Failed to copy to clipboard', 'error');
        }
        document.body.removeChild(textArea);
    }
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
        if (typeof ucmAlert !== 'undefined') {
            ucmAlert('Password must be at least 4 characters', 'Error');
        } else {
            showToast('Password must be at least 4 characters', 'error');
        }
        return;
    }
    
    if (password !== confirm) {
        if (typeof ucmAlert !== 'undefined') {
            ucmAlert('Passwords do not match', 'Error');
        } else {
            showToast('Passwords do not match', 'error');
        }
        return;
    }
    
    const { id, type } = window.pkcs12Params;
    
    if (!id || !type) {
        if (typeof ucmAlert !== 'undefined') {
            ucmAlert('Invalid PKCS#12 parameters', 'Error');
        } else {
            showToast('Invalid PKCS#12 parameters', 'error');
        }
        return;
    }
    
    // Build download URL using advanced export endpoint
    const baseUrl = type === 'ca' ? `/api/v1/ca/${id}/export/advanced` : `/api/v1/certificates/${id}/export/advanced`;
    const url = `${baseUrl}?format=pkcs12&key=true&password=${encodeURIComponent(password)}`;
    
    // Use exportWithToken to handle download with JWT cookies
    exportWithToken(url);
    
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
// EVENT DELEGATION - Modern approach without onclick
// ============================================================================

/**
 * Global click handler for all data-action elements
 * Attached once, works with dynamically loaded content
 * Uses capture phase to intercept BEFORE row onclick handlers
 */
document.addEventListener('click', (e) => {
    // Delete CA
    const deleteCABtn = e.target.closest('[data-action="delete-ca"]');
    if (deleteCABtn) {
        e.preventDefault();
        e.stopPropagation();
        const refid = deleteCABtn.dataset.refid;
        const name = deleteCABtn.dataset.name || deleteCABtn.dataset.descr;
        deleteCA(refid, name);
        return;
    }
    
    // Delete Certificate
    const deleteCertBtn = e.target.closest('[data-action="delete-cert"]');
    if (deleteCertBtn) {
        e.preventDefault();
        e.stopPropagation();
        const refid = deleteCertBtn.dataset.refid;
        const name = deleteCertBtn.dataset.name || deleteCertBtn.dataset.descr;
        deleteCert(refid, name);
        return;
    }
    
    // Revoke Certificate
    const revokeCertBtn = e.target.closest('[data-action="revoke-cert"]');
    if (revokeCertBtn) {
        e.preventDefault();
        e.stopPropagation();
        const refid = revokeCertBtn.dataset.refid;
        const name = revokeCertBtn.dataset.name || revokeCertBtn.dataset.descr;
        revokeCert(refid, name);
        return;
    }
    
    // Export CA
    const exportCABtn = e.target.closest('[data-action="export-ca"]');
    if (exportCABtn) {
        e.preventDefault();
        e.stopPropagation();
        const id = exportCABtn.dataset.id;
        exportCA(id, e);  // Pass event for menu positioning
        return;
    }
    
    // Export Certificate
    const exportCertBtn = e.target.closest('[data-action="export-cert"]');
    if (exportCertBtn) {
        e.preventDefault();
        e.stopPropagation();
        const id = exportCertBtn.dataset.id;
        const isCSR = exportCertBtn.dataset.isCsr === 'true';
        exportCert(id, e, isCSR);  // Pass event for menu positioning
        return;
    }
    
    // Export Certificate Simple
    const exportCertSimpleBtn = e.target.closest('[data-action="export-cert-simple"]');
    if (exportCertSimpleBtn) {
        e.preventDefault();
        e.stopPropagation();
        const id = exportCertSimpleBtn.dataset.id;
        exportCertSimple(id);
        return;
    }
    
    // Export Certificate with Key
    const exportCertKeyBtn = e.target.closest('[data-action="export-cert-key"]');
    if (exportCertKeyBtn) {
        e.preventDefault();
        e.stopPropagation();
        const id = exportCertKeyBtn.dataset.id;
        exportCertWithKey(id);
        return;
    }
    
    // Export Certificate with Chain
    const exportCertChainBtn = e.target.closest('[data-action="export-cert-chain"]');
    if (exportCertChainBtn) {
        e.preventDefault();
        e.stopPropagation();
        const id = exportCertChainBtn.dataset.id;
        exportCertWithChain(id);
        return;
    }
    
    // Export Certificate Full
    const exportCertFullBtn = e.target.closest('[data-action="export-cert-full"]');
    if (exportCertFullBtn) {
        e.preventDefault();
        e.stopPropagation();
        const id = exportCertFullBtn.dataset.id;
        exportCertFull(id);
        return;
    }
    
    // Export Certificate DER
    const exportCertDERBtn = e.target.closest('[data-action="export-cert-der"]');
    if (exportCertDERBtn) {
        e.preventDefault();
        e.stopPropagation();
        const id = exportCertDERBtn.dataset.id;
        exportCertDER(id);
        return;
    }
    
    // Show PKCS12 Modal
    const pkcs12Btn = e.target.closest('[data-action="show-pkcs12-modal"]');
    if (pkcs12Btn) {
        e.preventDefault();
        e.stopPropagation();
        const id = pkcs12Btn.dataset.id;
        const type = pkcs12Btn.dataset.type;
        showPKCS12ModalTable(id, type);
        return;
    }
    
    // Navigate to CA detail page
    const navigateCARow = e.target.closest('[data-action="navigate-ca"]');
    if (navigateCARow) {
        // Don't trigger if clicking on a button inside the row
        if (e.target.closest('button')) {
            return;
        }
        e.preventDefault();
        const caId = navigateCARow.dataset.caId;
        window.location.href = `/ca/${caId}`;
        return;
    }
    
    // Navigate to Certificate detail page
    const navigateCertRow = e.target.closest('[data-action="navigate-cert"]');
    if (navigateCertRow) {
        // Don't trigger if clicking on a button inside the row
        if (e.target.closest('button')) {
            return;
        }
        e.preventDefault();
        const certId = navigateCertRow.dataset.certId;
        window.location.href = `/certificates/${certId}`;
        return;
    }
    
    // Download CRL (from CRL list page)
    const downloadCRLListBtn = e.target.closest('[data-action="download-crl"]');
    if (downloadCRLListBtn) {
        e.preventDefault();
        e.stopPropagation();
        const caId = downloadCRLListBtn.dataset.caId;
        const format = downloadCRLListBtn.dataset.format;
        downloadCRL(caId, format);
        return;
    }
    
    // View CRL Info
    const viewCRLBtn = e.target.closest('[data-action="view-crl-info"]');
    if (viewCRLBtn) {
        e.preventDefault();
        e.stopPropagation();
        const refid = viewCRLBtn.dataset.refid;
        viewCRLInfo(refid);
        return;
    }
    
    // Generate CRL
    const generateCRLBtn = e.target.closest('[data-action="generate-crl"]');
    if (generateCRLBtn) {
        e.preventDefault();
        e.stopPropagation();
        const caId = generateCRLBtn.dataset.caId;
        const name = generateCRLBtn.dataset.name;
        generateCRL(caId, name);
        return;
    }
    
    // Approve SCEP
    const approveSCEPBtn = e.target.closest('[data-action="approve-scep"]');
    if (approveSCEPBtn) {
        e.preventDefault();
        e.stopPropagation();
        const txid = approveSCEPBtn.dataset.txid;
        approveSCEP(txid);
        return;
    }
    
    // Reject SCEP
    const rejectSCEPBtn = e.target.closest('[data-action="reject-scep"]');
    if (rejectSCEPBtn) {
        e.preventDefault();
        e.stopPropagation();
        const txid = rejectSCEPBtn.dataset.txid;
        rejectSCEP(txid);
        return;
    }
    
    // Sort Table CA
    const sortTableBtn = e.target.closest('[data-action="sort-table"]');
    if (sortTableBtn) {
        e.preventDefault();
        e.stopPropagation();
        const column = parseInt(sortTableBtn.dataset.column);
        sortTable(column);
        return;
    }
    
    // Sort Table Certificate
    const sortTableCertBtn = e.target.closest('[data-action="sort-table-cert"]');
    if (sortTableCertBtn) {
        e.preventDefault();
        e.stopPropagation();
        const column = parseInt(sortTableCertBtn.dataset.column);
        sortTableCert(column);
        return;
    }
    
    // Sort CA table (only ROOT CAs, not intermediates)
    const sortTableCABtn = e.target.closest('[data-action="sort-table-ca"]');
    if (sortTableCABtn) {
        e.preventDefault();
        e.stopPropagation();
        const column = parseInt(sortTableCABtn.dataset.column);
        sortTableCA(column);
        return;
    }
    
    // Update Certificate Pagination
    const updateCertPaginationSelect = e.target.closest('[data-action="update-cert-pagination"]');
    if (updateCertPaginationSelect) {
        updateCertPagination();
        return;
    }
    
    // Open Create CA Modal
    const openCreateCABtn = e.target.closest('[data-action="open-create-ca-modal"]');
    if (openCreateCABtn) {
        e.preventDefault();
        e.stopPropagation();
        openCreateCAModal();
        return;
    }
    
    // Open Import CA Modal
    const openImportCABtn = e.target.closest('[data-action="open-import-ca-modal"]');
    if (openImportCABtn) {
        e.preventDefault();
        e.stopPropagation();
        openImportCAModal();
        return;
    }
    
    // Open Create Cert Modal
    const openCreateCertBtn = e.target.closest('[data-action="open-create-cert-modal"]');
    if (openCreateCertBtn) {
        e.preventDefault();
        e.stopPropagation();
        openCreateCertModal();
        return;
    }
    
    // Open CSR Modal
    const openCSRBtn = e.target.closest('[data-action="open-csr-modal"]');
    if (openCSRBtn) {
        e.preventDefault();
        e.stopPropagation();
        openCSRModal();
        return;
    }
    
    // Close Create CA Modal
    const closeCreateCABtn = e.target.closest('[data-action="close-create-ca-modal"]');
    if (closeCreateCABtn) {
        e.preventDefault();
        e.stopPropagation();
        closeCreateCAModal();
        return;
    }
    
    // Close Import CA Modal
    const closeImportCABtn = e.target.closest('[data-action="close-import-ca-modal"]');
    if (closeImportCABtn) {
        e.preventDefault();
        e.stopPropagation();
        closeImportCAModal();
        return;
    }
    
    // Close Cert Modal
    const closeCertBtn = e.target.closest('[data-action="close-cert-modal"]');
    if (closeCertBtn) {
        e.preventDefault();
        e.stopPropagation();
        closeCertModal();
        return;
    }
    
    // Open Add User Modal
    const openAddUserBtn = e.target.closest('[data-action="open-add-user-modal"]');
    if (openAddUserBtn) {
        e.preventDefault();
        e.stopPropagation();
        openAddUserModal();
        return;
    }
    
    // Close Add User Modal
    const closeAddUserBtn = e.target.closest('[data-action="close-add-user-modal"]');
    if (closeAddUserBtn) {
        e.preventDefault();
        e.stopPropagation();
        closeAddUserModal();
        return;
    }
    
    // Change Password
    const changePasswordBtn = e.target.closest('[data-action="change-password"]');
    if (changePasswordBtn) {
        e.preventDefault();
        e.stopPropagation();
        const userId = changePasswordBtn.dataset.userId;
        const username = changePasswordBtn.dataset.username;
        openChangePasswordModal(userId, username);
        return;
    }
    
    // Close Change Password Modal
    const closeChangePasswordBtn = e.target.closest('[data-action="close-change-password-modal"]');
    if (closeChangePasswordBtn) {
        e.preventDefault();
        e.stopPropagation();
        closeChangePasswordModal();
        return;
    }
    
    // Change Role
    const changeRoleBtn = e.target.closest('[data-action="change-role"]');
    if (changeRoleBtn) {
        e.preventDefault();
        e.stopPropagation();
        const userId = changeRoleBtn.dataset.userId;
        const username = changeRoleBtn.dataset.username;
        const currentRole = changeRoleBtn.dataset.currentRole;
        openChangeRoleModal(userId, username, currentRole);
        return;
    }
    
    // Close Change Role Modal
    const closeChangeRoleBtn = e.target.closest('[data-action="close-change-role-modal"]');
    if (closeChangeRoleBtn) {
        e.preventDefault();
        e.stopPropagation();
        closeChangeRoleModal();
        return;
    }
    
    // Close CSR Modal
    const closeCSRBtn = e.target.closest('[data-action="close-csr-modal"]');
    if (closeCSRBtn) {
        e.preventDefault();
        e.stopPropagation();
        closeCSRModal();
        return;
    }
    
    // Close PKCS12 Modal
    const closePKCS12Btn = e.target.closest('[data-action="close-pkcs12-modal"]');
    if (closePKCS12Btn) {
        e.preventDefault();
        e.stopPropagation();
        closePKCS12Modal();
        return;
    }
    
    // Export PKCS12
    const exportPKCS12Btn = e.target.closest('[data-action="export-pkcs12"]');
    if (exportPKCS12Btn) {
        e.preventDefault();
        e.stopPropagation();
        exportPKCS12();
        return;
    }
    
    // Download PKCS12 with Password
    const downloadPKCS12Btn = e.target.closest('[data-action="download-pkcs12-with-password"]');
    if (downloadPKCS12Btn) {
        e.preventDefault();
        e.stopPropagation();
        downloadPKCS12WithPassword();
        return;
    }
    
    // Export CA variants
    const exportCASimpleBtn = e.target.closest('[data-action="export-ca-simple"]');
    if (exportCASimpleBtn) {
        e.preventDefault();
        e.stopPropagation();
        exportCASimple(exportCASimpleBtn.dataset.id);
        return;
    }
    
    const exportCAKeyBtn = e.target.closest('[data-action="export-ca-key"]');
    if (exportCAKeyBtn) {
        e.preventDefault();
        e.stopPropagation();
        exportCAWithKey(exportCAKeyBtn.dataset.id);
        return;
    }
    
    const exportCAChainBtn = e.target.closest('[data-action="export-ca-chain"]');
    if (exportCAChainBtn) {
        e.preventDefault();
        e.stopPropagation();
        exportCAWithChain(exportCAChainBtn.dataset.id);
        return;
    }
    
    const exportCAFullBtn = e.target.closest('[data-action="export-ca-full"]');
    if (exportCAFullBtn) {
        e.preventDefault();
        e.stopPropagation();
        exportCAFull(exportCAFullBtn.dataset.id);
        return;
    }
    
    const exportCADERBtn = e.target.closest('[data-action="export-ca-der"]');
    if (exportCADERBtn) {
        e.preventDefault();
        e.stopPropagation();
        exportCADER(exportCADERBtn.dataset.id);
        return;
    }
    
    // Show PKCS12 Modal from Table
    const showPKCS12TableBtn = e.target.closest('[data-action="show-pkcs12-modal-table"]');
    if (showPKCS12TableBtn) {
        e.preventDefault();
        e.stopPropagation();
        showPKCS12ModalTable(showPKCS12TableBtn.dataset.id, showPKCS12TableBtn.dataset.type);
        return;
    }
    
    // Toggle Export Menu (detail pages)
    const toggleExportBtn = e.target.closest('[data-action="toggle-export-menu"]');
    if (toggleExportBtn) {
        e.preventDefault();
        e.stopPropagation();
        if (typeof toggleExportMenu === 'function') {
            toggleExportMenu();
        }
        return;
    }
    
    // Download CRL PEM (from CA detail page)
    const downloadCRLDetailBtn = e.target.closest('[data-action="download-crl-pem"]');
    if (downloadCRLDetailBtn) {
        e.preventDefault();
        e.stopPropagation();
        const caId = downloadCRLDetailBtn.dataset.id;
        if (typeof downloadCRL === 'function') {
            downloadCRL(caId);
        }
        return;
    }
    
    // Toggle CDP Edit
    const toggleCDPBtn = e.target.closest('[data-action="toggle-cdp-edit"]');
    if (toggleCDPBtn) {
        e.preventDefault();
        e.stopPropagation();
        if (typeof toggleCDPEdit === 'function') {
            toggleCDPEdit();
        }
        return;
    }
    
    // Save CDP Config
    const saveCDPBtn = e.target.closest('[data-action="save-cdp-config"]');
    if (saveCDPBtn) {
        e.preventDefault();
        e.stopPropagation();
        if (typeof saveCDPConfig === 'function') {
            saveCDPConfig();
        }
        return;
    }
    
    // Cancel CDP Edit
    const cancelCDPBtn = e.target.closest('[data-action="cancel-cdp-edit"]');
    if (cancelCDPBtn) {
        e.preventDefault();
        e.stopPropagation();
        if (typeof cancelCDPEdit === 'function') {
            cancelCDPEdit();
        }
        return;
    }
    
    // Toggle OCSP Edit
    const toggleOCSPBtn = e.target.closest('[data-action="toggle-ocsp-edit"]');
    if (toggleOCSPBtn) {
        e.preventDefault();
        e.stopPropagation();
        if (typeof toggleOCSPEdit === 'function') {
            toggleOCSPEdit();
        }
        return;
    }
    
    // Save OCSP Config
    const saveOCSPBtn = e.target.closest('[data-action="save-ocsp-config"]');
    if (saveOCSPBtn) {
        e.preventDefault();
        e.stopPropagation();
        if (typeof saveOCSPConfig === 'function') {
            saveOCSPConfig();
        }
        return;
    }
    
    // Cancel OCSP Edit
    const cancelOCSPBtn = e.target.closest('[data-action="cancel-ocsp-edit"]');
    if (cancelOCSPBtn) {
        e.preventDefault();
        e.stopPropagation();
        if (typeof cancelOCSPEdit === 'function') {
            cancelOCSPEdit();
        }
        return;
    }
    
    // Set Theme
    const setThemeBtn = e.target.closest('[data-action="set-theme"]');
    if (setThemeBtn) {
        e.preventDefault();
        e.stopPropagation();
        const theme = setThemeBtn.dataset.theme;
        if (typeof setTheme === 'function' && theme) {
            setTheme(theme);
            if (typeof closeDropdown === 'function') {
                closeDropdown();
            }
        }
        return;
    }
    
    // Toggle Dropdown
    const toggleDropdownBtn = e.target.closest('[data-action="toggle-dropdown"]');
    if (toggleDropdownBtn) {
        e.preventDefault();
        e.stopPropagation();
        if (typeof toggleDropdown === 'function') {
            toggleDropdown();
        }
        return;
    }
    
    // Toggle Theme Variant (light/dark)
    const toggleVariantBtn = e.target.closest('[data-action="toggle-theme-variant"]');
    if (toggleVariantBtn) {
        e.preventDefault();
        e.stopPropagation();
        if (typeof toggleThemeVariant === 'function') {
            toggleThemeVariant();
        }
        if (typeof updateToggleIcon === 'function') {
            updateToggleIcon();
        }
        return;
    }
    
    // Generic onclick handler - for remaining onclick attributes
    // This allows templates to keep onclick temporarily while we migrate
    const onclickBtn = e.target.closest('[onclick]');
    if (onclickBtn) {
        const onclickAttr = onclickBtn.getAttribute('onclick');
        
        // Close modals
        if (onclickAttr.includes('closeCreateCAModal')) {
            e.preventDefault();
            e.stopPropagation();
            closeCreateCAModal();
            return;
        }
        if (onclickAttr.includes('closeImportCAModal')) {
            e.preventDefault();
            e.stopPropagation();
            closeImportCAModal();
            return;
        }
        if (onclickAttr.includes('closeCertModal')) {
            e.preventDefault();
            e.stopPropagation();
            closeCertModal();
            return;
        }
        if (onclickAttr.includes('closeCSRModal')) {
            e.preventDefault();
            e.stopPropagation();
            closeCSRModal();
            return;
        }
        if (onclickAttr.includes('closePKCS12Modal')) {
            e.preventDefault();
            e.stopPropagation();
            closePKCS12Modal();
            return;
        }
    }
}, true); // true = capture phase - intercept before inline onclick

// ============================================================================
// INITIALIZATION
// ============================================================================

// Auto-run on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ UCM Global Functions loaded');
    
    // Check for hash-based actions
    checkCreateHash();
    
    // Debug: Monitor all form submissions
    document.addEventListener('submit', function(e) {
        console.log('🔥 Form submit detected:', e.target.id || 'unnamed form', e);
        const formData = new FormData(e.target);
        console.log('Form data:', Object.fromEntries(formData.entries()));
    }, true);
});

// Re-run after HTMX swaps (for SPA navigation)
document.addEventListener('htmx:afterSwap', function() {
    checkCreateHash();
});

console.log('📦 UCM Global Functions module loaded');
