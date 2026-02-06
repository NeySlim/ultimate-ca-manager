/**
 * Error Boundary - Catch React errors gracefully
 */
import { Component } from 'react'
import { Warning, ArrowClockwise } from '@phosphor-icons/react'

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo })
    // Log to console in development
    if (import.meta.env.DEV) {
      console.error('ErrorBoundary caught:', error, errorInfo)
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null })
    // Optionally reload the page
    if (this.props.onReset) {
      this.props.onReset()
    }
  }

  render() {
    if (this.state.hasError) {
      // Custom fallback UI
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] p-8 text-center">
          <div className="w-16 h-16 rounded-full status-danger-bg flex items-center justify-center mb-4">
            <Warning size={32} className="status-danger-text" />
          </div>
          <h2 className="text-lg font-semibold text-text-primary mb-2">
            Something went wrong
          </h2>
          <p className="text-sm text-text-secondary mb-4 max-w-md">
            An unexpected error occurred. Please try again or refresh the page.
          </p>
          {import.meta.env.DEV && this.state.error && (
            <pre className="text-xs text-left bg-bg-tertiary p-3 rounded-md mb-4 max-w-lg overflow-auto text-status-danger">
              {this.state.error.toString()}
            </pre>
          )}
          <button
            onClick={this.handleReset}
            className="flex items-center gap-2 px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-primary/90 transition-colors"
          >
            <ArrowClockwise size={16} />
            Try Again
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
