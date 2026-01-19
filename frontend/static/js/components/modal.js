class Modal {
  constructor(options = {}) {
    this.title = options.title || 'Dialog';
    this.content = options.content || '';
    this.onClose = options.onClose || (() => {});
    this.onConfirm = options.onConfirm || null;
    this.confirmText = options.confirmText || 'Confirm';
    this.confirmType = options.confirmType || 'primary'; // primary, danger
    
    this.element = null;
    this.render();
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'modal-overlay';
    
    const footerButtons = `
      <button class="btn btn-ghost js-close">Cancel</button>
      ${this.onConfirm ? `<button class="btn btn-${this.confirmType} js-confirm">${this.confirmText}</button>` : ''}
    `;

    this.element.innerHTML = `
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">${this.title}</h3>
          <button class="modal-close js-close">${Icons.get('x', 20)}</button>
        </div>
        <div class="modal-body">
          ${this.content}
        </div>
        <div class="modal-footer">
          ${footerButtons}
        </div>
      </div>
    `;

    document.body.appendChild(this.element);
    
    // Bind events
    this.element.querySelectorAll('.js-close').forEach(el => {
      el.addEventListener('click', () => this.close());
    });
    
    if (this.onConfirm) {
      this.element.querySelector('.js-confirm').addEventListener('click', () => {
        this.onConfirm();
        this.close();
      });
    }

    // Close on click outside
    this.element.addEventListener('click', (e) => {
      if (e.target === this.element) this.close();
    });

    // Trigger animation
    requestAnimationFrame(() => {
      this.element.classList.add('open');
    });
  }

  close() {
    this.element.classList.remove('open');
    setTimeout(() => {
      if (this.element.parentNode) {
        this.element.parentNode.removeChild(this.element);
      }
      this.onClose();
    }, 300);
  }
}

window.Modal = Modal;
