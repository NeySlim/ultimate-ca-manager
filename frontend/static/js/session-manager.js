/**
 * Session Expiration Warning System
 * Warns user before session expires and allows extension
 */

class SessionManager {
    constructor() {
        // Get session duration from localStorage (in minutes), default to 30 minutes
        const sessionMinutes = parseInt(localStorage.getItem('ucm-session-duration')) || 30;
        this.sessionDuration = sessionMinutes * 60 * 1000; // Convert to milliseconds
        this.warningTime = 2 * 60 * 1000; // Show warning 2 minutes before expiration
        this.lastActivity = Date.now();
        this.warningTimer = null;
        this.expirationTimer = null;
        this.modalVisible = false;
        
        console.log('SessionManager initialized with duration:', sessionMinutes, 'minutes');
        
        this.init();
    }
    
    init() {
        // Track user activity
        this.setupActivityListeners();
        
        // Get initial session state from server, then start timers
        this.initializeFromServer();
        
        // Create warning modal
        this.createModal();
        
        // Periodic check with server
        setInterval(() => this.checkServerSession(), 60000); // Every minute
    }
    
    initializeFromServer() {
        htmx.ajax('GET', '/api/session/check', {
            swap: 'none',
            headers: {
                'Content-Type': 'application/json'
            }
        }).then(() => {
            // Success handled by event listener
        }).catch(() => {
            console.error('Failed to initialize from server');
            this.lastActivity = Date.now();
            console.log('Starting timers...');
            this.resetTimers();
        });
        
        // Handle success response
        document.addEventListener('htmx:afterOnLoad', (event) => {
            if (event.detail.pathInfo.requestPath === '/api/session/check' && event.detail.successful) {
                try {
                    const data = JSON.parse(event.detail.xhr.responseText);
                    console.log('Session check response:', data);
                    
                    if (data.last_activity) {
                        // Calculate time elapsed since last activity on server
                        const serverLastActivity = data.last_activity * 1000; // Convert to milliseconds
                        const now = Date.now();
                        const elapsed = now - serverLastActivity;
                        
                        console.log('Server last activity:', new Date(serverLastActivity).toLocaleString());
                        console.log('Time elapsed since last activity:', Math.round(elapsed / 1000), 'seconds');
                        console.log('Time until expiration:', Math.round((this.sessionDuration - elapsed) / 1000), 'seconds');
                        console.log('Time until warning:', Math.round((this.sessionDuration - this.warningTime - elapsed) / 1000), 'seconds');
                        
                        // Adjust our timer to match server
                        this.lastActivity = now - elapsed;
                    } else {
                        // No last_activity from server, use current time
                        console.log('No last_activity from server, using current time');
                        this.lastActivity = Date.now();
                    }
                } catch (e) {
                    console.error('Failed to parse session check response:', e);
                    this.lastActivity = Date.now();
                }
                
                // Now start the timers with correct time
                console.log('Starting timers...');
                this.resetTimers();
            } else if (event.detail.pathInfo.requestPath === '/api/session/check' && !event.detail.successful) {
                // Server error, use current time
                console.log('Server error, using current time');
                this.lastActivity = Date.now();
                console.log('Starting timers...');
                this.resetTimers();
            }
        }, { once: false });
    }
    
    setupActivityListeners() {
        // Reset timers on user activity
        const events = ['mousedown', 'keydown', 'scroll', 'touchstart', 'click'];
        events.forEach(event => {
            document.addEventListener(event, () => this.onActivity(), { passive: true });
        });
        
        // Reset on HTMX requests (navigation)
        document.addEventListener('htmx:afterSwap', () => this.onActivity());
    }
    
    onActivity() {
        const now = Date.now();
        // Only update if more than 10 seconds since last activity (avoid spam)
        if (now - this.lastActivity > 10000) {
            this.lastActivity = now;
            this.resetTimers();
            
            // Ping server to extend session
            this.extendSession(true); // silent = true
        }
    }
    
    resetTimers() {
        // Clear existing timers
        if (this.warningTimer) clearTimeout(this.warningTimer);
        if (this.expirationTimer) clearTimeout(this.expirationTimer);
        
        // Hide modal if visible
        if (this.modalVisible) {
            this.hideModal();
        }
        
        // Calculate time since last activity
        const now = Date.now();
        const timeSinceLastActivity = now - this.lastActivity;
        
        // Calculate remaining time until warning and expiration
        const timeUntilExpiration = this.sessionDuration - timeSinceLastActivity;
        const timeUntilWarning = timeUntilExpiration - this.warningTime;
        
        console.log('resetTimers called:');
        console.log('  Time since last activity:', Math.round(timeSinceLastActivity / 1000), 'seconds');
        console.log('  Time until expiration:', Math.round(timeUntilExpiration / 1000), 'seconds');
        console.log('  Time until warning:', Math.round(timeUntilWarning / 1000), 'seconds');
        
        // SAFETY: Never show warning if session is less than 1 minute old
        if (timeSinceLastActivity < 60000) {
            console.log('  Session is very recent (< 1 min), forcing full duration timers');
            const fullTimeUntilWarning = this.sessionDuration - this.warningTime;
            this.warningTimer = setTimeout(() => this.showWarning(), fullTimeUntilWarning);
            this.expirationTimer = setTimeout(() => this.expireSession(), this.sessionDuration);
            return;
        }
        
        // Only set timers if there's time left
        if (timeUntilWarning > 0) {
            console.log('  Setting warning timer for', Math.round(timeUntilWarning / 1000), 'seconds');
            this.warningTimer = setTimeout(() => this.showWarning(), timeUntilWarning);
        } else if (timeUntilExpiration > 0) {
            // Less than warning time left, show warning immediately
            console.log('  Less than warning time left, showing warning immediately');
            this.showWarning();
        } else {
            // Already expired
            console.log('  Session already expired!');
            this.expireSession();
            return;
        }
        
        if (timeUntilExpiration > 0) {
            console.log('  Setting expiration timer for', Math.round(timeUntilExpiration / 1000), 'seconds');
            this.expirationTimer = setTimeout(() => this.expireSession(), timeUntilExpiration);
        } else {
            // Already expired
            console.log('  Session already expired!');
            this.expireSession();
        }
    }
    
    showWarning() {
        if (this.modalVisible) return;
        
        this.modalVisible = true;
        const modal = document.getElementById('session-warning-modal');
        const countdown = document.getElementById('session-countdown');
        
        if (modal) {
            // Show modal with flex display
            modal.style.display = 'flex';
            
            // Calculate actual time remaining until expiration
            const now = Date.now();
            const timeSinceLastActivity = now - this.lastActivity;
            const timeUntilExpiration = this.sessionDuration - timeSinceLastActivity;
            let secondsLeft = Math.max(0, Math.floor(timeUntilExpiration / 1000));
            
            console.log('Showing session warning. Seconds left:', secondsLeft);
            
            // Update countdown immediately
            if (countdown) {
                const minutes = Math.floor(secondsLeft / 60);
                const seconds = secondsLeft % 60;
                countdown.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
            }
            
            // Start countdown
            const countdownInterval = setInterval(() => {
                secondsLeft--;
                if (countdown) {
                    const minutes = Math.floor(secondsLeft / 60);
                    const seconds = secondsLeft % 60;
                    countdown.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
                }
                
                if (secondsLeft <= 0 || !this.modalVisible) {
                    clearInterval(countdownInterval);
                    if (secondsLeft <= 0) {
                        this.expireSession();
                    }
                }
            }, 1000);
        }
    }
    
    hideModal() {
        this.modalVisible = false;
        const modal = document.getElementById('session-warning-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }
    
    extendSession(silent = false) {
        htmx.ajax('POST', '/api/ui/session/extend', {
            swap: 'none',
            headers: {
                'Content-Type': 'application/json'
            }
        }).then(() => {
            this.lastActivity = Date.now();
            this.resetTimers();
            
            if (!silent) {
                this.showNotification('Session prolongée de 30 minutes', 'success');
            }
            return true;
        }).catch((error) => {
            console.error('Failed to extend session:', error);
            // Network error - assume session expired
            this.redirectToLogin();
            return false;
        });
        
        // Handle 401 (session expired)
        document.addEventListener('htmx:responseError', (event) => {
            if (event.detail.pathInfo.requestPath === '/api/ui/session/extend' && event.detail.xhr.status === 401) {
                this.redirectToLogin();
            }
        }, { once: false });
    }
    
    checkServerSession() {
        htmx.ajax('GET', '/api/session/check', {
            swap: 'none',
            headers: {
                'Content-Type': 'application/json'
            }
        }).then(() => {
            // Session OK, nothing to do
        }).catch((error) => {
            console.error('Failed to check session:', error);
        });
        
        // Handle 401 (session expired)
        document.addEventListener('htmx:responseError', (event) => {
            if (event.detail.pathInfo.requestPath === '/api/session/check' && event.detail.xhr.status === 401) {
                this.redirectToLogin();
            }
        }, { once: false });
    }
    
    redirectToLogin() {
        // Clear timers to prevent further execution
        if (this.warningTimer) clearTimeout(this.warningTimer);
        if (this.expirationTimer) clearTimeout(this.expirationTimer);
        
        // Hide modal if visible
        this.hideModal();
        
        // Redirect immediately without notification
        window.location.href = '/logout?expired=1';
    }
    
    expireSession() {
        // Clear timers
        if (this.warningTimer) clearTimeout(this.warningTimer);
        if (this.expirationTimer) clearTimeout(this.expirationTimer);
        
        // Hide modal
        this.hideModal();
        
        // Show expiration message
        this.showNotification('Votre session a expiré', 'error');
        
        // Redirect to logout after 2 seconds
        setTimeout(() => {
            window.location.href = '/logout?expired=1';
        }, 2000);
    }
    
    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `session-notification session-notification-${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 80px;
            right: 20px;
            padding: 16px 24px;
            background: ${type === 'error' ? 'var(--status-danger)' : 'var(--status-success)'};
            color: white;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 10000;
            animation: slideIn 0.3s ease;
            font-weight: 500;
        `;
        
        document.body.appendChild(notification);
        
        // Remove after 3 seconds
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }
    
    createModal() {
        // Check if modal already exists, don't create duplicate
        if (document.getElementById('session-warning-modal')) {
            console.log('Session modal already exists, skipping creation');
            return;
        }
        
        // Create modal HTML
        const modalHTML = `
            <div id="session-warning-modal" style="display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 9999; align-items: center; justify-content: center; background: rgba(0,0,0,0.5);">
                <div style="background: var(--card-bg); border-radius: 12px; padding: 32px; max-width: 500px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); border: 1px solid var(--border-color);">
                    <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 20px;">
                        <div style="width: 48px; height: 48px; border-radius: 50%; background: rgba(239, 68, 68, 0.1); display: flex; align-items: center; justify-content: center;">
                            <svg class="ucm-icon" width="24" height="24" style="color: var(--status-danger);">
                                <use href="#icon-warning-triangle"/>
                            </svg>
                        </div>
                        <div>
                            <h3 style="font-size: 20px; font-weight: 600; color: var(--text-primary); margin: 0;">Session bientôt expirée</h3>
                            <p style="font-size: 14px; color: var(--text-secondary); margin: 4px 0 0 0;">Temps restant: <span id="session-countdown" style="font-weight: 600; color: var(--status-danger);">2:00</span></p>
                        </div>
                    </div>
                    
                    <p style="color: var(--text-secondary); margin: 0 0 24px 0; line-height: 1.6;">
                        Votre session va expirer dans quelques instants. Cliquez sur "Prolonger" pour rester connecté, sinon vous serez automatiquement déconnecté.
                    </p>
                    
                    <div style="display: flex; gap: 12px; justify-content: flex-end;">
                        <button onclick="sessionManager.expireSession()" class="btn btn-secondary">
                            <i class="fas fa-sign-out"></i>
                            <span>Se déconnecter</span>
                        </button>
                        <button onclick="sessionManager.extendSession(false)" class="btn btn-primary">
                            <i class="fas fa-clock"></i>
                            <span>Prolonger la session</span>
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // Add to body
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        
        // Add animations
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
    }
}

// Initialize session manager when DOM is ready
let sessionManager;
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        sessionManager = new SessionManager();
    });
} else {
    sessionManager = new SessionManager();
}
