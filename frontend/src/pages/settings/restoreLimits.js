// Largest file the restore picker accepts, from the server's announced ceilings; 0 = no client ceiling.
export function restoreMaxBytes(limits) {
  if (!limits) return 0
  const { archive_bytes: archive = 0, upload_bytes: upload = 0 } = limits
  if (!archive) return 0
  return Math.max(archive, upload)
}
