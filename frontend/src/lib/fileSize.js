// A byte count as the file picker shows it: KB, MB, then GB with one decimal.
export function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(0)}MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)}GB`
}
