/** The aria-describedby of a sign-in field: its hint ids, then its error (`err-<id>`) when there is one. */
export const describedBy = (id, error, ...hints) => [...hints, error && `err-${id}`].filter(Boolean).join(' ') || undefined
