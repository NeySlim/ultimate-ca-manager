class Sidebar {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.render();
  }
  render() {
    this.container.innerHTML = `
      <aside class="app-sidebar">
        <div class="sidebar-header">
          <h1 style="font-weight: 700; font-size: 20px;">UCM</h1>
        </div>
        <div class="sidebar-content">
          <nav class="nav-menu">
            ${this.renderNavItem('dashboard', 'Dashboard', 'dashboard', true)}
            ${this.renderNavItem('certificates', 'Certificates', 'certificate')}
            ${this.renderNavItem('users', 'Users & Teams', 'users')}
            ${this.renderNavItem('settings', 'Settings', 'settings')}
          </nav>
        </div>
        <div class="sidebar-footer">
           <div style="display: flex; align-items: center; gap: 10px;">
             <div style="width: 32px; height: 32px; border-radius: 50%; background: #ddd;"></div>
             <div style="flex: 1; overflow: hidden;">
               <div style="font-size: 13px; font-weight: 600;">Admin User</div>
             </div>
             <button onclick="ThemeManager.toggle()" style="padding: 4px;">
               ${Icons.get('moon', 16)}
             </button>
           </div>
        </div>
      </aside>
    `;
  }
  renderNavItem(id, label, iconName, isActive = false) {
    const style = `display: flex; align-items: center; gap: 12px; padding: 10px 12px; margin-bottom: 4px; border-radius: var(--radius-sm); color: ${isActive ? 'var(--text-primary)' : 'var(--text-secondary)'}; background: ${isActive ? 'var(--bg-active)' : 'transparent'}; cursor: pointer;`;
    return `<a href="#${id}" class="nav-item ${isActive ? 'active' : ''}" style="${style}">${Icons.get(iconName, 18)}<span style="font-size: 14px; font-weight: 500;">${label}</span></a>`;
  }
}
window.Sidebar = Sidebar;
