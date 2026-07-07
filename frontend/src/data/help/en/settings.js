export default {
  helpContent: {
    title: 'Settings',
    subtitle: 'System configuration',
    overview:
      'Configure all aspects of the UCM system. Settings are organized by category: general, appearance, email, security, SSO, backup, audit, database, HTTPS, updates, and webhooks.',
    sections: [
      {
        title: 'Prometheus metrics',
        content:
          'Opt-in /metrics endpoint exposing certificate, CA, scheduler, webhook and ACME counters in Prometheus format.',
        items: [
          {
            label: 'Enable',
            text: 'Set a metrics token in Settings › General; without a token the endpoint returns 404 (disabled)',
          },
          { label: 'Auth', text: 'Scrape with Authorization: Bearer <token>' },
          {
            label: 'Counters',
            text: 'ucm_certificates, ucm_certificate_authorities, ucm_scheduler_task_*, ucm_webhook_deliveries, ucm_acme_*',
          },
        ],
      },
      {
        title: 'Public ACME vhost',
        content:
          'Settings › General: public hostname and port for ACME directory URLs behind a reverse proxy.',
        items: [
          { label: 'Admin', text: 'admin.ucm.example.com — GUI and API (mTLS per policy)' },
          {
            label: 'ACME',
            text: 'acme.ucm.example.com — /acme/* and /acme/proxy/* (no client mTLS)',
          },
          {
            label: 'Wildcard',
            text: 'A *.ucm.example.com certificate covers admin.ucm.example.com and acme.ucm.example.com, not the apex ucm.example.com',
          },
          {
            label: 'TLS certificate ID',
            text: 'Metadata for the certificate deployed on the ACME vhost (e.g. wildcard)',
          },
        ],
      },
      {
        title: 'Webhook delivery history',
        content:
          'Each webhook endpoint keeps a delivery log with status, attempts and a manual retry.',
        items: [
          {
            label: 'Statuses',
            text: 'pending / delivered / failed, with the last HTTP code and error',
          },
          { label: 'Retry', text: 'Manually re-queue a failed or already-delivered event' },
          {
            label: 'Async',
            text: 'Deliveries run from a durable queue with exponential backoff (up to 5 attempts)',
          },
        ],
      },
      {
        title: 'Scheduler view',
        content: 'Settings › System lists the background tasks with their status and last run.',
        items: [
          {
            label: 'Tasks',
            text: 'Expiry checks, CRL refresh, webhook delivery, scheduled backups, auto-renewal, etc.',
          },
          { label: 'Run now', text: 'Trigger any task on demand' },
          {
            label: 'Visibility',
            text: 'Last run, last duration and failure count per task',
          },
        ],
      },
      {
        title: 'Scheduled backups',
        content: 'Automatic, encrypted database backups on a configurable cadence with retention.',
        items: [
          { label: 'Cadence', text: 'Daily / weekly / monthly' },
          { label: 'Retention', text: 'Keep the N most recent backups; older ones are pruned' },
          { label: 'Encryption', text: 'Backups are encrypted with the configured backup password' },
        ],
      },
      {
        title: 'HSTS (Strict Transport Security)',
        content:
          'Operator-configurable HSTS policy so instances serving self-signed certificates during setup can opt out entirely.',
        items: [
          { label: 'Default', text: 'HSTS on, includeSubDomains, max-age 1 year (backward compatible)' },
          {
            label: 'Disable',
            text: 'Turn off for instances with self-signed certs during initial setup (avoids browser lock-out)',
          },
          {
            label: 'Env override',
            text: 'UCM_HSTS_ENABLED, UCM_HSTS_INCLUDE_SUBDOMAINS, UCM_HSTS_MAX_AGE in /etc/ucm/ucm.env win over the DB setting',
          },
          {
            label: 'Subdomains',
            text: 'Drop includeSubDomains when subdomains host separate services with their own certs',
          },
        ],
      },
      {
        title: 'Categories',
        items: [
          { label: 'General', text: 'Instance name, hostname, and system-wide defaults' },
          { label: 'Appearance', text: 'Theme selection (light/dark/system), accent color, desktop mode' },
          {
            label: 'Email (SMTP)',
            text: 'SMTP server, credentials, email template editor, and expiry alert notifications',
          },
          { label: 'Security', text: 'Password policies, session timeout, rate limiting, IP restrictions' },
          { label: 'SSO', text: 'SAML 2.0, OAuth2/OIDC, and LDAP single sign-on integration' },
          { label: 'Backup', text: 'Manual and scheduled database backups' },
          { label: 'Audit', text: 'Log retention, syslog forwarding, integrity verification' },
          {
            label: 'Database',
            text: 'Active backend (SQLite or PostgreSQL), size, table count, test/switch/migrate between backends',
          },
          { label: 'HTTPS', text: 'TLS certificate for the UCM web interface' },
          { label: 'Updates', text: 'Check for new versions, view changelog, auto-update (DEB/RPM)' },
          {
            label: 'Webhooks',
            text: 'HTTP webhooks for certificate events (issue, revoke, expire). Optional outbound auth: Bearer, Basic, API key, or custom header',
          },
        ],
      },
      {
        title: 'SMTP OAuth2 (XOAUTH2)',
        content:
          'Modern OAuth2 authentication for outbound mail, replacing legacy app-password flows that Microsoft and Google are deprecating:',
        items: [
          {
            label: 'Gmail',
            text: 'Configure a Google Cloud OAuth2 client with the https://mail.google.com/ scope',
          },
          {
            label: 'Microsoft 365 / Outlook.com',
            text: 'Register an Azure AD app with SMTP.Send delegated permission',
          },
          {
            label: 'Refresh tokens',
            text: 'UCM stores the refresh token and renews access tokens automatically before each send',
          },
          { label: 'Fallback', text: 'Password auth is still supported when OAuth2 is not configured' },
        ],
      },
    ],
    tips: [
      'Use the System Status widget at the top to quickly check service health',
      'Test SMTP settings before relying on email notifications',
      'Customize the email template with your branding using the built-in HTML/Text editor',
      'Schedule automatic backups for production environments',
      'Switching SQLite ↔ PostgreSQL is bidirectional — the UI runs safety checks (driver loaded, target reachable, target empty) before migrating',
    ],
    warnings: [
      'Changing the HTTPS certificate requires a service restart',
      'Modifying security settings may lock out users — verify access before saving',
    ],
  },
  helpGuides: {
    title: 'Settings',
    content: `
## Overview

System-wide configuration organized into tabs. Changes take effect immediately unless noted otherwise.

## General

- **Instance Name** — Displayed in the browser title and emails
- **Hostname** — The server's fully qualified domain name
- **Default Validity** — Default certificate validity period in days
- **Expiry Warning Threshold** — Days before expiry to trigger warnings
- **Public ACME vhost** — Hostname advertised in ACME directory URLs (e.g. \`acme.ucm.example.com\`). A wildcard \`*.ucm.example.com\` certificate typically covers both \`admin.ucm.example.com\` (admin UI) and \`acme.ucm.example.com\` (ACME endpoints without client mTLS). It does not cover the apex \`ucm.example.com\` unless that name is explicitly in the certificate SAN.

## HTTPS

Manage the TLS certificate used by the UCM web interface:
- View the current certificate details
- Import a new certificate (PEM or PKCS#12)
- Generate a self-signed certificate

> ⚠ Changing the HTTPS certificate requires a service restart.

See the full Settings guide in helpGuides for SMTP, SSO, database migration, webhooks, and Prometheus metrics.
`,
  },
}
