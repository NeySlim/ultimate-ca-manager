/** The validity typed in the field, as the server takes it; empty or unreadable is the default year. */
export const validityDays = (value) => Number.parseInt(String(value ?? ''), 10) || 365
