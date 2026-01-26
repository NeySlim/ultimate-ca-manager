import { useState } from 'react'
import { User, Plus, Eye, Trash } from '@phosphor-icons/react'
import './Users.css'

export default function Users() {
  const [users, setUsers] = useState([
    { id: 1, username: 'admin', email: 'admin@ucm.local', role: 'admin', status: 'active', lastLogin: '2024-01-26 10:30' },
    { id: 2, username: 'operator1', email: 'operator@ucm.local', role: 'operator', status: 'active', lastLogin: '2024-01-25 14:22' },
    { id: 3, username: 'viewer1', email: 'viewer@ucm.local', role: 'viewer', status: 'active', lastLogin: '2024-01-24 09:15' }
  ])
  const [showCreateModal, setShowCreateModal] = useState(false)
  
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
              <th>Last Login</th>
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
                <td>{user.email}</td>
                <td><span className={`role-badge ${user.role}`}>{user.role}</span></td>
                <td><span className="status-badge success">{user.status}</span></td>
                <td className="text-secondary">{user.lastLogin}</td>
                <td className="user-actions">
                  <button className="icon-btn"><Eye size={16} /></button>
                  <button className="icon-btn danger"><Trash size={16} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      {showCreateModal && (
        <CreateUserModal onClose={() => setShowCreateModal(false)} onCreate={() => setShowCreateModal(false)} />
      )}
    </div>
  )
}

function CreateUserModal({ onClose, onCreate }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create User</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="form-group">
            <label>Username</label>
            <input type="text" placeholder="john.doe" />
          </div>
          <div className="form-group">
            <label>Email</label>
            <input type="email" placeholder="john.doe@example.com" />
          </div>
          <div className="form-group">
            <label>Role</label>
            <select>
              <option value="admin">Admin (Full access)</option>
              <option value="operator">Operator (Manage certificates)</option>
              <option value="viewer">Viewer (Read only)</option>
            </select>
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" placeholder="Min 8 characters" />
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={onCreate}>Create User</button>
        </div>
      </div>
    </div>
  )
}
