export default function ErrorMessage({ message, onRetry }) {
  return (
    <div className="error-container">
      <p className="error-text">⚠️ {message}</p>
      {onRetry && (
        <button className="btn-primary" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}
