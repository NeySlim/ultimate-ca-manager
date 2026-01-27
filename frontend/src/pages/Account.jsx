import { useState, useEffect } from 'react'
import { User, Lock, Bell } from '@phosphor-icons/react'
import { api } from '../lib/api'

export default function Account() {
  const [user, setUser] = useState(null)
  const [password, setPassword] = useState({ current: '', new: '', confirm: '' })
  
  useEffect(() => {
    fetchUser()
  }, [])
  
  async function fetchUser() {
    try {
      const data = await api.getCurrentUser()
      setUser(data)
    } catch (err) {
      console.error(err)
    }
  }
  
  async function handlePasswordChange(e) {
    e.preventDefault()
    if (password.new !== password.confirm) {
      alert('Passwords do not match')
      return
    }
    try {
      await api.changePassword(password.current, password.new)
      alert('Password changed successfully')
      setPassword({ current: '', new: '', confirm: '' })
    } catch (err) {
      alert(err.message)
    }
  }
  
  return (
    <div className="account-page">
      <h1>Account Settings</h1>
      <p className="subtitle">Manage your profile and preferences</p>
      
      <div className="account-grid">
        <div className="profile-section">
          <h2><User size={20} /> Profile Information</h2>
          <div className="profile-card">
            <div className="form-group">
              <label>USERNAME</label>
              <input type="text" value={user?.username || ''} disabled />
            </div>
            <div className="form-group">
              <label>EMAIL</label>
              <input type="email" value={user?.email || ''} disabled />
            </div>
            <div className="form-group">
              <label>ROLE</label>
              <span className={`badge ${user?.role}`}>{user?.role || 'user'}</span>
            </div>
          </div>
        </div>
        
        <div className="password-section">
          <h2><Lock size={20} /> Change Password</h2>
          <form className="password-form" onSubmit={handlePasswordChange}>
            <div className="form-group">
              <label>CURRENT PASSWORD*</label>
              <input 
                type="password" 
                value={password.current}
                onChange={e => setPassword({...password, current: e.target.value})}
                required
              />
            </div>
            <div className="form-group">
              <label>NEW PASSWORD*</label>
              <input 
                type="password" 
                value={password.new}
                onChange={e => setPassword({...password, new: e.target.value})}
                required
              />
            </div>
            <div className="form-group">
              <label>CONFIRM PASSWORD*</label>
              <input 
                type="password" 
                value={password.confirm}
                onChange={e => setPassword({...password, confirm: e.target.value})}
                required
              />
            </div>
            <button type="submit" className="btn-primary">Update Password</button>
          </form>
        </div>
        
        <div className="notifications-section">
          <h2><Bell size={20} /> Notifications</h2>
          <div className="notification-options">
            <label className="checkbox-label">
              <input type="checkbox" defaultChecked />
              Email notifications for expiring certificates
            </label>
            <label className="checkbox-label">
              <input type="checkbox" defaultChecked />
              Alert on certificate issuance
            </label>
            <label className="checkbox-label">
              <input type="checkbox" />
              Daily summary reports
            </label>
          </div>
        </div>
      </div>
    </div>
  )
}
