import React from 'react';
import { Card } from './ui/Card';
import { Button } from './ui/Button';
import styles from './ErrorBoundary.module.css';

/**
 * Error Boundary Component
 * Catches React errors and displays a fallback UI
 */
export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ error, errorInfo });
    console.error('Error caught by boundary:', error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleGoHome = () => {
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className={styles.errorBoundary}>
          <Card className={styles.errorCard}>
            <Card.Body>
              <div className={styles.errorIcon}>
                <i className="ph ph-warning-circle" />
              </div>
              <h1 className={styles.errorTitle}>Something went wrong</h1>
              <p className={styles.errorMessage}>
                The application encountered an unexpected error. Please try refreshing the page.
              </p>
              
              {this.state.error && (
                <details className={styles.errorDetails}>
                  <summary>Error Details</summary>
                  <pre className={styles.errorStack}>
                    {this.state.error.toString()}
                    {this.state.errorInfo?.componentStack}
                  </pre>
                </details>
              )}

              <div className={styles.errorActions}>
                <Button variant="primary" icon="ph ph-arrow-clockwise" onClick={this.handleReload}>
                  Reload Page
                </Button>
                <Button variant="default" icon="ph ph-house" onClick={this.handleGoHome}>
                  Go to Dashboard
                </Button>
              </div>
            </Card.Body>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
