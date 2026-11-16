// UCM fields an attribute mapping row can target (same list as the backend).
const UCM_FIELDS = ['username', 'email', 'fullname', 'groups']

// The backend reads a mapping's "groups" rows of the form `attribute -> groups` in place of
// legacy `groups -> attribute` ones. Once a form row exists, rewrite each legacy row into the
// form's shape so that adding a group source never silently stops another one being read.
export function keepLegacyGroupsRead(mapping) {
  const next = mapping || {}
  const hasFormRow = Object.entries(next).some(([key, val]) => val === 'groups' && key !== 'groups')
  const legacy = next.groups
  if (!hasFormRow || typeof legacy !== 'string' || !legacy.trim() || UCM_FIELDS.includes(legacy.trim())) return next
  const attribute = legacy.trim()
  if (Object.prototype.hasOwnProperty.call(next, attribute)) return next
  const { groups: _legacy, ...rest } = next
  return { ...rest, [attribute]: 'groups' }
}
