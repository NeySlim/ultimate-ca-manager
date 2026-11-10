/**
 * Section selector shared by the detail panels. `all` renders every block;
 * any other value renders only the blocks tagged with that name.
 */
export const DETAIL_SECTIONS = ['all', 'overview', 'chain', 'extensions', 'pem']

export const showSection = (section, ...names) =>
  section === 'all' || names.includes(section)
