import { useState, useEffect } from 'react'
import { User, Plus } from '@phosphor-icons/react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'
import './Users.css'

export default function Users() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  
  useEffect(() => {
    fetchUsers()
  }, [])
  
  async function fetchUsers() {
    try {
      setLoading(true)
      setError(null)
      const data = await api.getUsers()
      setUsers(data || [])
    } catch (err) {
      console.error('Users fetch error:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  if (loading) return <LoadingSpinner message="Loading users..." />
  if (error) return <ErrorMessage message={error} onRetry={fetchUsers} />
  
  return (
    <div className="users-page">
      <div className="page-header">
        <div>
          <h1>Users</h1>
          <p className="subtitle">{users.length} users total</p>
        </div>
        <button className="btn-primary" onClick={() => setShowCreateModal(true)}>
          <Plus size={16} />
          Create User
        </button>
      </div>
      
      <div className="users-table-container">
        <table className="users-table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map(user => (
              <tr key={user.id}>
                <td className="user-cell">
                  <User size={16} />
                  <span>{user.username}</span>
                </td>
                <td>{user.email || 'N/A'}</td>
                <td><span className={`role-badge ${user.role || 'viewer'}`}>{user.role || 'viewer'}</span></td>
                <td><span className="status-badge success">{user.status || 'active'}</span></td>
                <td className="user-actions">
                  <button className="icon-btn">Edit</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      {showCreateModal && <CreateUserModal onClose={() => setShowCreateModal(false)} onCreate={fetchUsers} />}
    </div>
  )
}

function CreateUserModal({ onClose, onCreate }) {
  const [formData, setFormData] = useState({ username: '', email: '', password: '', role: 'viewer' })
  
  async function handleSubmit(e) {
    e.preventDefault()
    try {
      await api.createUser(formData)
      onCreate()
      onClose()
    } catch (err) {
      alert('Error: ' + err.message)
    }
  }
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create User</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label>Username</label>
              <input type="text" required value={formData.username} onChange={e => setFormData({...formData, username: e.target.value})} />
            </div>
            <div className="form-group">
              <label>Email</label>
              <input type="email" value={formData.email} onChange={e => setFormData({...formData, email: e.target.value})} />
            </div>
            <div className="form-group">
              <label>Role</label>
              <select value={formData.role} onChange={e => setFormData({...formData, role: e.target.value})}>
                <option value="admin">Admin</option>
                <option value="operator">Operator</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>
            <div className="form-group">
              <label>Password</label>
              <input type="password" required value={formData.password} onChange={e => setFormData({...formData, password: e.target.value})} />
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Create</button>
          </div>
        </form>
      </div>
    </div>
  )
}
