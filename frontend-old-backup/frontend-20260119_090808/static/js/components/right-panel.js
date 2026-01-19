class RightPanel {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.render();
  }
  render() {
    this.container.innerHTML = `
      <aside class="app-right-panel">
        <div style="padding: var(--space-md); border-bottom: 1px solid var(--border-light);">
          <h3 style="font-size: 14px; font-weight: 600; text-transform: uppercase; color: var(--text-secondary);">Stats</h3>
        </div>
        <div style="padding: var(--space-md);">
           <div class="stat-item" style="margin-bottom: 16px;">
             <div style="font-size: 24px; font-weight: 700;">1,248</div>
             <div style="font-size: 12px; color: var(--text-secondary);">Active Certificates</div>
           </div>
        </div>
      </aside>
    `;
  }
}
window.RightPanel = RightPanel;
