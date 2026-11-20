/** The name of a built-in role in the interface language; any other role keeps its own name. */
const BUILT_IN = { admin: 'users.admin', operator: 'common.operator', auditor: 'common.auditor', viewer: 'common.viewer' }
// Languages whose nouns keep their capital inside a sentence
const CAPITALISED_NOUNS = ['de']

export function roleLabel(t, role) {
  if (!role) return ''
  return BUILT_IN[role] ? t(BUILT_IN[role]) : String(role)
}

/** The role inside a sentence ("Signed in: Alice Martin, operator."): a built-in name in lower case. */
export function roleInSentence(t, role, language = 'en') {
  const label = roleLabel(t, role)
  const lang = String(language || 'en').split('-')[0]
  return BUILT_IN[role] && !CAPITALISED_NOUNS.includes(lang) ? label.toLocaleLowerCase(lang) : label
}
