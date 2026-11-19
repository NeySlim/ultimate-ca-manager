/** Fixtures of the CAs page tests: a small hierarchy and an installation of 139 authorities. */
const FAR = '2040-01-01T00:00:00Z'

export const ca = (id, over = {}) => ({
  id, refid: `ref-${id}`, name: `CA ${id}`, common_name: `CA ${id}`, subject: `CN=CA ${id}`,
  type: 'root', status: 'Active', certs: 0, valid_to: FAR, cross_certificate_count: 0, ...over,
})

/** Root 1 > Services (12 certs) > [Internal, Legacy]; Root 1 > Identities; Root 2 alone with 3 certs. */
export const smallHierarchy = () => [
  ca(1, { name: 'Example Root' }),
  ca(2, { name: 'Services', type: 'intermediate', parent_id: 1, certs: 12 }),
  ca(3, { name: 'Internal', type: 'intermediate', parent_id: 2, certs: 5 }),
  ca(4, { name: 'Legacy', type: 'intermediate', parent_id: 2, certs: 4, status: 'Expired', valid_to: '2020-01-01T00:00:00Z' }),
  ca(5, { name: 'Identities', type: 'intermediate', parent_id: 1, certs: 8 }),
  ca(6, { name: 'Second Root', certs: 3, offline: true }),
]

/** 139 authorities: 131 roots (2 with a subtree, 9 alone with certificates, 120 idle and named alike), 8 intermediates. */
export function largeInstallation() {
  const list = [
    ca(1, { name: 'Example Root' }),
    ca(2, { name: 'Example Root G2' }),
    ...[3, 4, 5, 6, 7].map((id) => ca(id, { name: `Issuing ${id}`, type: 'intermediate', parent_id: 1, certs: id })),
    ...[8, 9, 10].map((id) => ca(id, { name: `Issuing ${id}`, type: 'intermediate', parent_id: 2, certs: 1 })),
  ]
  for (let id = 11; id <= 19; id += 1) list.push(ca(id, { name: `Standalone ${id}`, certs: 2 }))
  for (let id = 20; id <= 139; id += 1) list.push(ca(id, { name: 'smoke test ca' }))
  return list
}
