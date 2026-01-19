class Topbar {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.render();
  }
  render() {
    this.container.innerHTML = `
      <header class="app-topbar">
        <div class="topbar-left" style="display: flex; gap: 20px;">
          <div class="nav-tabs" style="display: flex; gap: 8px;">
            <button class="tab active" style="padding: 6px 12px; border-radius: var(--radius-sm); background: var(--bg-active); font-weight: 500; font-size: 13px;">Overview</button>
            <button class="tab" style="padding: 6px 12px; border-radius: var(--radius-sm); color: var(--text-secondary); font-size: 13px;">Details</button>
          </div>
        </div>
        <div class="topbar-right" style="display: flex; align-items: center; gap: 12px;">
           <div class="search-bar" style="position: relative;">
             <span style="position: absolute; left: 8px; top: 50%; transform: translateY(-50%); color: var(--text-secondary);">${Icons.get('search', 14)}</span>
             <input type="text" placeholder="Search..." style="padding: 6px 8px 6px 28px; border-radius: var(--radius-sm); border: 1px solid var(--border-light); background: var(--bg-primary); font-size: 13px; width: 200px;">
           </div>
           <button class="btn-primary" style="background: var(--magenta); color: white; padding: 6px 12px; border-radius: var(--radius-sm); font-size: 13px; font-weight: 500; display: flex; align-items: center; gap: 6px;">
             ${Icons.get('plus', 14)} <span>Create</span>
           </button>
        </div>
      </header>
    `;
  }
}
window.Topbar = Topbar;
