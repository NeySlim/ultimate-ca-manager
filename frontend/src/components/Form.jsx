/**
 * Form Component - Form wrapper with validation
 */
import { useState } from 'react'
import { Button } from './Button'
import { LoadingSpinner } from './LoadingSpinner'

export function Form({ 
  onSubmit, 
  initialValues = {}, 
  children,
  submitLabel = 'Submit',
  cancelLabel = 'Cancel',
  onCancel,
  showCancel = true,
  className 
}) {
  const [values, setValues] = useState(initialValues)
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setErrors({})

    try {
      await onSubmit(values)
    } catch (error) {
      if (error.errors) {
        setErrors(error.errors)
      }
    } finally {
      setLoading(false)
    }
  }

  const handleChange = (name, value) => {
    setValues(prev => ({ ...prev, [name]: value }))
    if (errors[name]) {
      setErrors(prev => {
        const newErrors = { ...prev }
        delete newErrors[name]
        return newErrors
      })
    }
  }

  return (
    <form onSubmit={handleSubmit} className={className}>
      <div className="space-y-4">
        {typeof children === 'function' 
          ? children({ values, errors, handleChange, setValues })
          : children
        }
      </div>

      <div className="flex justify-end gap-3 mt-6 pt-6 border-t border-border">
        {showCancel && (
          <Button
            type="button"
            variant="ghost"
            onClick={onCancel}
            disabled={loading}
          >
            {cancelLabel}
          </Button>
        )}
        <Button type="submit" disabled={loading}>
          {loading ? <LoadingSpinner size="sm" /> : submitLabel}
        </Button>
      </div>
    </form>
  )
}
