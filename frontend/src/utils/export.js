/**
 * Export utilities for downloading data as various formats
 */

/**
 * Download a file with the given content
 */
export function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Convert array of objects to CSV string
 */
export function convertToCSV(data, columns = null) {
  if (!data || data.length === 0) return '';

  // Use provided columns or extract from first object
  const headers = columns || Object.keys(data[0]);
  
  // Escape CSV values
  const escape = (value) => {
    if (value === null || value === undefined) return '';
    const str = String(value);
    // Escape quotes and wrap in quotes if contains comma, quote, or newline
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };

  // Build CSV
  const headerRow = headers.join(',');
  const rows = data.map(row => 
    headers.map(header => escape(row[header])).join(',')
  );

  return [headerRow, ...rows].join('\n');
}

/**
 * Export data as CSV
 */
export function exportAsCSV(data, filename, columns = null) {
  const csv = convertToCSV(data, columns);
  const timestamp = new Date().toISOString().split('T')[0];
  downloadFile(csv, `${filename}-${timestamp}.csv`, 'text/csv;charset=utf-8;');
}

/**
 * Export data as JSON
 */
export function exportAsJSON(data, filename) {
  const json = JSON.stringify(data, null, 2);
  const timestamp = new Date().toISOString().split('T')[0];
  downloadFile(json, `${filename}-${timestamp}.json`, 'application/json');
}

/**
 * Export table data with optional column filtering
 * Automatically cleans up internal fields (starting with _)
 */
export function exportTableData(data, filename, options = {}) {
  const {
    format = 'csv',
    columns = null,
    excludeColumns = ['_raw', '_internal'],
  } = options;

  // Clean up data
  const cleanData = data.map(row => {
    const cleaned = {};
    Object.keys(row).forEach(key => {
      // Skip excluded columns and internal fields
      if (!key.startsWith('_') && !excludeColumns.includes(key)) {
        cleaned[key] = row[key];
      }
    });
    return cleaned;
  });

  // Export based on format
  if (format === 'json') {
    exportAsJSON(cleanData, filename);
  } else {
    exportAsCSV(cleanData, filename, columns);
  }
}
