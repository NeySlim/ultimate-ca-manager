// The message for an audit chain verification result: { level, key, params }.
export function integrityMessage(data) {
  const protection = data.protection || {};
  if (!data.valid) {
    const errors = data.error_count ?? data.errors?.length ?? 0;
    if (data.first_error_code === 'not_sealed_by_key') {
      return { level: 'error', key: 'audit.integrityUnsealedAfterKey', params: { id: data.first_error_id, errors } };
    }
    if (data.first_error_id) {
      return { level: 'error', key: 'audit.integrityBroken', params: { id: data.first_error_id, errors } };
    }
    return { level: 'error', key: 'audit.integrityFailed', params: { errors } };
  }
  if (data.status === 'unprotected') {
    return {
      level: 'warning', key: 'audit.integrityUnprotected',
      params: { count: data.checked, unprotected: protection.not_attested ?? data.checked },
    };
  }
  if (protection.key_rotation_id) {
    return {
      level: 'success', key: 'audit.integrityIntactRotated',
      params: { id: protection.protected_from_id, rotation: protection.key_rotation_id, older: protection.not_attested },
    };
  }
  if (protection.not_attested) {
    return {
      level: 'success', key: 'audit.integrityIntactPartial',
      params: { id: protection.protected_from_id, count: protection.protected, older: protection.not_attested },
    };
  }
  return { level: 'success', key: 'audit.integrityVerified', params: { count: data.checked } };
}
