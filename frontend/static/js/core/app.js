document.addEventListener('DOMContentLoaded', async () => {
  // Initialize Layout Components
  new Sidebar('sidebar-container');
  new Topbar('topbar-container');
  new RightPanel('right-panel-container');

  const grid = document.getElementById('main-content');
  
  // Loader
  grid.innerHTML = '<div style="padding: 20px; text-align: center; grid-column: 1/-1;">Loading certificates...</div>';

  try {
    // Attempt to fetch real data
    const response = await API.certs.list();
    const certs = response.items || response.data || response || []; // Handle various formats

    grid.innerHTML = '';
    
    if (certs.length === 0) {
       grid.innerHTML = '<div style="padding: 20px; text-align: center; grid-column: 1/-1;">No certificates found. Create one!</div>';
       return;
    }

    certs.forEach(cert => {
      const card = document.createElement('div');
      card.className = 'card';
      
      // Determine status color
      const statusColor = cert.status === 'valid' ? 'var(--success)' : 'var(--warning)';
      const expiryDate = new Date(cert.not_after || Date.now()).toLocaleDateString();
      
      card.innerHTML = `
        <div class="card-header">
           <div class="card-title" style="display: flex; align-items: center; gap: 8px;">
             <span style="width: 8px; height: 8px; border-radius: 50%; background: ${statusColor}"></span>
             ${cert.common_name || cert.name || 'Unknown Cert'}
           </div>
           <button class="btn btn-ghost btn-sm">${Icons.get('more-vertical', 16)}</button>
        </div>
        <div class="card-body">
           <div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 4px;">Serial: ${(cert.serial_number || '').substring(0, 10)}...</div>
           <div style="font-size: 13px; color: var(--text-secondary);">Expires: ${expiryDate}</div>
        </div>
        <div class="card-footer" style="display: flex; justify-content: flex-end; gap: 8px;">
           <button class="btn btn-secondary btn-sm">Details</button>
           <button class="btn btn-secondary btn-sm">Download</button>
        </div>
      `;
      grid.appendChild(card);
    });

  } catch (err) {
    console.error('Failed to load certs:', err);
    // If it's a 401, api.js handles redirect. For other errors:
    if (err.message !== 'Unauthorized') {
        grid.innerHTML = `
          <div style="grid-column: 1/-1; padding: 20px; background: rgba(255,0,0,0.1); border-radius: 8px; color: var(--error);">
            Error loading certificates: ${err.message}
            <br><br>
            <button class="btn btn-secondary" onclick="window.location.reload()">Retry</button>
          </div>
        `;
        
        // Fallback: render dummy data for demo purposes if real API fails (non-auth error)
        renderDummyData(grid);
    }
  }
});

function renderDummyData(container) {
  const dummyTitle = document.createElement('h3');
  dummyTitle.style.cssText = 'grid-column: 1/-1; margin-top: 20px; opacity: 0.5; text-align: center; text-transform: uppercase; font-size: 12px;';
  dummyTitle.innerText = 'Demo Data (Backend Unavailable)';
  container.appendChild(dummyTitle);

  for (let i = 0; i < 4; i++) {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <div class="card-header">
         <div class="card-title">Demo Certificate ${i+1}</div>
         <button class="btn btn-ghost btn-sm">${Icons.get('more-vertical', 16)}</button>
      </div>
      <div class="card-body">
         <div style="font-size: 13px; color: var(--text-secondary);">Simulated data</div>
      </div>
    `;
    container.appendChild(card);
  }
}
