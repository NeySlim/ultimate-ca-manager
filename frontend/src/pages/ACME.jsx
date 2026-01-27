import { useState, useEffect } from 'react'
import { ShieldCheck, Plus, Trash, Key } from '@phosphor-icons/react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'
import './ACME.css'

export default function ACME() {
  const [accounts, setAccounts] = useState([])
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newAccount, setNewAccount] = useState({ email: '', provider: 'letsencrypt' })
  
  useEffect(() => {
    fetchData()
  }, [])
  
  async function fetchData() {
    try {
      setLoading(true)
      setError(null)
      const [accts, ords] = await Promise.all([
        api.getACMEAccounts().catch(() => []),
        api.getACMEOrders().catch(() => [])
      ])
      setAccounts(accts || [])
      setOrders(ords || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  async function handleCreate() {
    try {
      await api.createACMEAccount(newAccount)
      setShowCreateModal(false)
      setNewAccount({ email: '', provider: 'letsencrypt' })
      fetchData()
    } catch (err) {
      alert(err.message)
    }
  }
  
  async function handleDelete(id) {
    if (!confirm('Delete this ACME account?')) return
    try {
      await api.deleteACMEAccount(id)
      fetchData()
    } catch (err) {
      alert(err.message)
    }
  }
  
  if (loading) return <LoadingSpinner message="Loading ACME..." />
  if (error) return <ErrorMessage message={error} onRetry={fetchData} />
  
  return (
    <div className="acme-page">
      <div className="page-header">
        <div>
          <h1>ACME Automation</h1>
          <p className="subtitle">Automated certificate issuance via ACME protocol</p>
        </div>
        <button className="btn-primary" onClick={() => setShowCreateModal(true)}>
          <Plus size={20} weight="bold" />
          New Account
        </button>
      </div>
      
      <div className="acme-grid">
        <div className="accounts-section">
          <h2>ACME Accounts</h2>
          {accounts.length === 0 ? (
            <div className="empty-state">
              <ShieldCheck size={48} weight="duotone" />
              <p>No ACME accounts configured</p>
              <button className="btn-secondary" onClick={() => setShowCreateModal(true)}>
                Create First Account
              </button>
            </div>
          ) : (
            <div className="accounts-list">
              {accounts.map(acc => (
                <div key={acc.id} className="account-card">
                  <div className="account-header">
                    <Key size={24} weight="duotone" />
                    <div className="account-info">
                      <h3>{acc.email}</h3>
                      <span className="provider-badge">{acc.provider || 'Let\'s Encrypt'}</span>
                    </div>
                  </div>
                  <div className="account-stats">
                    <div className="stat">
                      <span className="label">Status</span>
                      <span className={`badge ${acc.status}`}>{acc.status || 'active'}</span>
                    </div>
                    <div className="stat">
                      <span className="label">Certificates</span>
                      <span className="value">{acc.cert_count || 0}</span>
                    </div>
                  </div>
                  <button className="btn-icon-danger" onClick={() => handleDelete(acc.id)} title="Delete">
                    <Trash size={18} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        
        <div className="orders-section">
          <h2>Recent Orders</h2>
          {orders.length === 0 ? (
            <p className="empty-message">No recent ACME orders</p>
          ) : (
            <div className="orders-list">
              {orders.map(order => (
                <div key={order.id} className="order-item">
                  <div className="order-info">
                    <strong>{order.domain || order.identifier}</strong>
                    <span className="order-time">{order.created_at}</span>
                  </div>
                  <span className={`badge ${order.status}`}>{order.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-container" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create ACME Account</h2>
              <button className="modal-close" onClick={() => setShowCreateModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Email*</label>
                <input 
                  type="email" 
                  placeholder="admin@example.com"
                  value={newAccount.email}
                  onChange={e => setNewAccount({...newAccount, email: e.target.value})}
                />
              </div>
              <div className="form-group">
                <label>Provider*</label>
                <select value={newAccount.provider} onChange={e => setNewAccount({...newAccount, provider: e.target.value})}>
                  <option value="letsencrypt">Let's Encrypt</option>
                  <option value="zerossl">ZeroSSL</option>
                  <option value="buypass">Buypass</option>
                </select>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowCreateModal(false)}>Cancel</button>
              <button className="btn-primary" onClick={handleCreate}>Create Account</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
