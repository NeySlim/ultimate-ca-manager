class Toast {
  static container = null;

  static init() {
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.className = 'toast-container';
      document.body.appendChild(this.container);
    }
  }

  static show(message, type = 'info', duration = 3000) {
    this.init();
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    // Icon selection
    let iconName = 'info';
    if (type === 'success') iconName = 'check'; // Need to ensure check icon exists
    if (type === 'error') iconName = 'x';
    if (type === 'warning') iconName = 'alert-triangle'; // Need icon
    
    // Add missing icons if needed in icons.js, for now use fallback logic inside Icons.get
    
    toast.innerHTML = `
      <div class="toast-icon">${Icons.get(iconName, 20)}</div>
      <div class="toast-message">${message}</div>
      <div class="toast-close">${Icons.get('x', 16)}</div>
    `;
    
    this.container.appendChild(toast);
    
    // Close button
    toast.querySelector('.toast-close').addEventListener('click', () => {
      this.remove(toast);
    });

    // Auto remove
    if (duration > 0) {
      setTimeout(() => {
        this.remove(toast);
      }, duration);
    }
  }

  static remove(toast) {
    toast.style.animation = 'slideUp 0.3s ease reverse forwards';
    toast.addEventListener('animationend', () => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    });
  }
  
  static success(msg, duration) { this.show(msg, 'success', duration); }
  static error(msg, duration) { this.show(msg, 'error', duration); }
  static info(msg, duration) { this.show(msg, 'info', duration); }
}

window.Toast = Toast;
