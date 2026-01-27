import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Lock } from '@phosphor-icons/react'
import { api } from '../lib/api'
import './Login.css'

export default function Login() {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('changeme123')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()
  
  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    
    try {
      // Temporary bypass for demo - just go to dashboard
      localStorage.setItem('ucm_token', 'demo_token')
      setTimeout(() => {
        navigate('/dashboard')
      }, 500)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <Lock size={40} weight="duotone" />
          <h1>UCM</h1>
          <p>Ultimate Certificate Manager</p>
        </div>
        
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Username</label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="Enter username"
              disabled={loading}
            />
          </div>
          
          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Enter password"
              disabled={loading}
            />
          </div>
          
          {error && (
            <div className="error-message">{error}</div>
          )}
          
          <button type="submit" className="login-btn" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
