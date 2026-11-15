// Largest file the restore picker accepts, from the server's announced ceilings; 0 = no client ceiling.
export function restoreMaxBytes(limits) {
  if (!limits) return 0
  const { archive_bytes: archive = 0, upload_bytes: upload = 0 } = limits
  if (!archive) return 0
  return Math.max(archive, upload)
}

const MAGIC = [0x55, 0x43, 0x4d, 0x42] // "UCMB"
const LEGACY_VERSIONS = new Set([2, 3])

function readHead(file, length) {
  const blob = file.slice(0, length)
  if (typeof blob.arrayBuffer === 'function') return blob.arrayBuffer()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(reader.error)
    reader.readAsArrayBuffer(blob)
  })
}

// The ceiling the server applies to this file's format (services/backup/storage.py
// restore_size_refusal) when the file exceeds it, else null. A header it cannot
// place (v1, not an archive) is left to the server.
export async function restoreLegacyCeilingExceeded(file, limits) {
  const upload = limits?.upload_bytes || 0
  if (!upload || !file || file.size <= upload) return null
  let head
  try {
    head = new Uint8Array(await readHead(file, 5))
  } catch {
    return null
  }
  if (head.length < 5 || MAGIC.some((byte, i) => head[i] !== byte)) return null
  return LEGACY_VERSIONS.has(head[4]) ? upload : null
}
