const Auth = {
  async login(username, password) {
    const btn = document.querySelector('.btn-login');
    const originalText = btn.innerHTML;
    
    try {
      btn.innerHTML = '<span class="spinner"></span> Signing in...';
      btn.style.opacity = '0.8';
      btn.disabled = true;

      await API.auth.login(username, password);
      
      Toast.success('Login successful! Redirecting...');
      
      setTimeout(() => {
        window.location.href = './'; // Redirect to root (dashboard)
      }, 500);

    } catch (error) {
      console.error(error);
      Toast.error(error.message || 'Login failed. Please check credentials.');
      
      btn.innerHTML = originalText;
      btn.style.opacity = '1';
      btn.disabled = false;
      
      // Shake animation on card
      const card = document.querySelector('.login-card');
      card.classList.add('shake');
      setTimeout(() => card.classList.remove('shake'), 500);
    }
  },

  async mtls() {
    Toast.info('Connecting with mTLS...');
    // In real scenario, browser handles cert prompt automatically.
    // We just hit the endpoint.
    try {
      await API.post('auth/mtls');
      window.location.href = './';
    } catch (e) {
      Toast.error('mTLS Certificate not accepted or missing.');
    }
  },

  async webauthn() {
    Toast.info('WebAuthn not fully implemented in this demo.');
  }
};

document.getElementById('login-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const inputs = e.target.querySelectorAll('input');
  const username = inputs[0].value;
  const password = inputs[1].value;
  
  if (!username || !password) {
    Toast.warning('Please enter both username and password');
    return;
  }
  
  Auth.login(username, password);
});

// Add Shake animation style
const style = document.createElement('style');
style.textContent = `
  @keyframes shake {
    0%, 100% { transform: translateX(0); }
    10%, 30%, 50%, 70%, 90% { transform: translateX(-5px); }
    20%, 40%, 60%, 80% { transform: translateX(5px); }
  }
  .shake { animation: shake 0.5s cubic-bezier(.36,.07,.19,.97) both; }
  .spinner {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid rgba(255,255,255,0.3);
    border-radius: 50%;
    border-top-color: white;
    animation: spin 1s ease-in-out infinite;
    margin-right: 8px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
`;
document.head.appendChild(style);

window.Auth = Auth;
