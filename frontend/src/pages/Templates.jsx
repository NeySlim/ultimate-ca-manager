import { useState, useEffect } from 'react'
import { FileText, Plus, Copy, Trash, Pencil } from '@phosphor-icons/react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorMessage from '../components/ErrorMessage'
import './Templates.css'

export default function Templates() {
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editTemplate, setEditTemplate] = useState(null)
  
  useEffect(() => {
    fetchTemplates()
  }, [])
  
  async function fetchTemplates() {
    try {
      setLoading(true)
      setError(null)
      const data = await api.getTemplates()
      setTemplates(data || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  async function handleDuplicate(id) {
    try {
      await api.duplicateTemplate(id)
      fetchTemplates()
    } catch (err) {
      alert(err.message)
    }
  }
  
  async function handleDelete(id) {
    if (!confirm('Delete this template?')) return
    try {
      await api.deleteTemplate(id)
      fetchTemplates()
    } catch (err) {
      alert(err.message)
    }
  }
  
  if (loading) return <LoadingSpinner message="Loading templates..." />
  if (error) return <ErrorMessage message={error} onRetry={fetchTemplates} />
  
  return (
    <div className="templates-page">
      <div className="page-header">
        <div>
          <h1>Certificate Templates</h1>
          <p className="subtitle">Reusable certificate configurations</p>
        </div>
        <button className="btn-primary">
          <Plus size={20} weight="bold" />
          New Template
        </button>
      </div>
      
      {templates.length === 0 ? (
        <div className="empty-state">
          <FileText size={48} weight="duotone" />
          <p>No templates created yet</p>
          <button className="btn-secondary">Create First Template</button>
        </div>
      ) : (
        <div className="templates-grid">
          {templates.map(tpl => (
            <div key={tpl.id} className="template-card">
              <div className="template-header">
                <FileText size={24} weight="duotone" />
                <h3>{tpl.name}</h3>
              </div>
              <p className="template-description">{tpl.description || 'No description'}</p>
              <div className="template-details">
                <div className="detail">
                  <span className="label">Type</span>
                  <span className="value">{tpl.type || 'Server'}</span>
                </div>
                <div className="detail">
                  <span className="label">Validity</span>
                  <span className="value">{tpl.validity_days || 365} days</span>
                </div>
                <div className="detail">
                  <span className="label">Usage</span>
                  <span className="badge">{tpl.usage_count || 0}</span>
                </div>
              </div>
              <div className="template-actions">
                <button className="btn-icon" onClick={() => handleDuplicate(tpl.id)} title="Duplicate">
                  <Copy size={18} />
                </button>
                <button className="btn-icon" onClick={() => handleDelete(tpl.id)} title="Delete">
                  <Trash size={18} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function CreateTemplateModal({ onClose, onCreate }) {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    key_usage: [],
    extended_key_usage: [],
    validity_days: 365
  })
  
  async function handleSubmit(e) {
    e.preventDefault()
    try {
      await api.createTemplate(formData)
      onCreate()
      onClose()
    } catch (err) {
      alert('Error: ' + err.message)
    }
  }
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-large" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create Certificate Template</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label>Template Name *</label>
              <input 
                type="text" 
                required 
                value={formData.name}
                onChange={e => setFormData({...formData, name: e.target.value})}
                placeholder="Web Server Certificate"
              />
            </div>
            
            <div className="form-group">
              <label>Description</label>
              <textarea 
                value={formData.description}
                onChange={e => setFormData({...formData, description: e.target.value})}
                placeholder="Template for issuing web server SSL/TLS certificates"
                rows={3}
              />
            </div>
            
            <div className="form-group">
              <label>Validity (days)</label>
              <input 
                type="number"
                min="1"
                max="3650"
                value={formData.validity_days}
                onChange={e => setFormData({...formData, validity_days: parseInt(e.target.value)})}
              />
            </div>
            
            <div className="form-group">
              <label>Key Usage</label>
              <div className="checkbox-group">
                {['digitalSignature', 'keyEncipherment', 'dataEncipherment'].map(usage => (
                  <label key={usage} className="checkbox-label">
                    <input 
                      type="checkbox"
                      checked={formData.key_usage.includes(usage)}
                      onChange={e => {
                        if (e.target.checked) {
                          setFormData({...formData, key_usage: [...formData.key_usage, usage]})
                        } else {
                          setFormData({...formData, key_usage: formData.key_usage.filter(u => u !== usage)})
                        }
                      }}
                    />
                    {usage}
                  </label>
                ))}
              </div>
            </div>
          </div>
          
          <div className="modal-footer">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Create Template</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function EditTemplateModal({ template, onClose, onUpdate }) {
  const [formData, setFormData] = useState({
    name: template.name || '',
    description: template.description || '',
    validity_days: template.validity_days || 365
  })
  
  async function handleSubmit(e) {
    e.preventDefault()
    try {
      await api.updateTemplate(template.id, formData)
      onUpdate()
      onClose()
    } catch (err) {
      alert('Error: ' + err.message)
    }
  }
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-large" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Edit Template: {template.name}</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label>Template Name *</label>
              <input 
                type="text" 
                required 
                value={formData.name}
                onChange={e => setFormData({...formData, name: e.target.value})}
              />
            </div>
            
            <div className="form-group">
              <label>Description</label>
              <textarea 
                value={formData.description}
                onChange={e => setFormData({...formData, description: e.target.value})}
                rows={3}
              />
            </div>
            
            <div className="form-group">
              <label>Validity (days)</label>
              <input 
                type="number"
                min="1"
                max="3650"
                value={formData.validity_days}
                onChange={e => setFormData({...formData, validity_days: parseInt(e.target.value)})}
              />
            </div>
          </div>
          
          <div className="modal-footer">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Update Template</button>
          </div>
        </form>
      </div>
    </div>
  )
}
