# Detail panels

Rule: a panel is pure, actions live in the hook, content is split in sections.

- **Pure panel.** `CertificatePanel`, `CAPanel`, `TrustCertPanel` and `CSRPanel`
  only render the entity they are given. No service call, no modal, no action
  button (a static test checks that nothing here imports a service). The rule
  covers direct imports: field components that load their own data are known
  exceptions, to be absorbed at the inspector lot: `SignatureSchemeField`,
  `ComplianceProfileField`, `IssuanceVisibilityField`, `CrossCertificatesSection`,
  `CACrlSection`, `ChainUsageSection` and `CertDeploySection`.
- **Actions in the hook.** `hooks/useEntityActions` returns `{ actions, modals,
  refresh, handler }` for a `type` and an `entity`: the ordered action list
  (with visibility from permissions and entity state), the modals they open,
  and the `ucm:data-changed` notification after a mutation. `ActionBar` renders
  the list. Containers (the floating window, page slide-overs) assemble
  `ActionBar` + panel + `modals`.
- **Sections.** Every panel takes `section` in `all | overview | chain |
  extensions | pem` (default `all`). A panel renders the blocks of that section
  and nothing else; a section it does not have renders nothing. See `sections.js`.

Caller-owned buttons (a CSR's sign or rekey row) are passed as `children` of
`CSRPanel` and `TrustCertPanel`; they are not props of the panel.
