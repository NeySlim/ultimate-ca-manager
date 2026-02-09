# UCM Project Instructions

## Repository

**Single repository**: `/root/ucm-src/` → `NeySlim/ultimate-ca-manager`

- **Branch main**: production releases
- **Branch 2.1.0-dev**: development

### ⚠️ CRITICAL
- **Code in**: `/root/ucm-src/`
- **Test on**: netsuit (local), pve (DEB:8445, Docker:8444), fedor (RPM:8443)

---

## Deployment

### ⚠️ Development vs Package Testing
- **Development**: Deploy to **netsuit:8443** (local machine)
- **Package Testing**: Deploy to pve (DEB), fedor (RPM) only for testing packages

### Build Frontend
```bash
cd /root/ucm-src/frontend && npm run build
```

### Deploy to netsuit (DEV - port 8443)
```bash
sudo rm -rf /opt/ucm/frontend/dist/*
sudo cp -r /root/ucm-src/frontend/dist/* /opt/ucm/frontend/dist/
sudo cp -r /root/ucm-src/backend/* /opt/ucm/backend/
sudo systemctl restart ucm
```
URL: https://netsuit.lan.pew.pet:8443

### Deploy to pve (DEB package test - port 8445)
```bash
ssh pve "rm -rf /opt/ucm/frontend/dist/*"
scp -rq /root/ucm-src/frontend/dist/* pve:/opt/ucm/frontend/dist/
scp -rq /root/ucm-src/backend/* pve:/opt/ucm/backend/
ssh pve "systemctl restart ucm"
```

### Deploy to fedor (RPM package test - port 8443)
```bash
ssh fedor "rm -rf /opt/ucm/frontend/dist/*"
scp -rq /root/ucm-src/frontend/dist/* fedor:/opt/ucm/frontend/dist/
scp -rq /root/ucm-src/backend/* fedor:/opt/ucm/backend/
ssh fedor "systemctl restart ucm"
```

### Deploy to Docker (pve:8444)
```bash
CONTAINER_ID=$(ssh pve "docker ps -q --filter 'publish=8444'")
ssh pve "docker cp - $CONTAINER_ID:/app/frontend/" < <(cd /root/ucm-src/frontend && tar -cf - dist)
```

---

## Git Workflow

### Development (default)
Push to **2.1.0-dev only** for all regular work:
```bash
cd /root/ucm-src
git add -A && git commit -m "type(scope): message"
git push origin 2.1.0-dev
```

### Release (explicit user request only)
Push to **main** only when user explicitly says "release" or "push to production":
```bash
git push origin 2.1.0-dev:main
```

### ⚠️ NEVER push to main automatically
- main = production releases only
- 2.1.0-dev = all development work
- Ask user before pushing to main

---

## Test Environments

| Type | Host | Port | Usage |
|------|------|------|-------|
| DEV | netsuit | 8443 | Daily development |
| DEB | pve | 8445 | Package testing only |
| Docker | pve | 8444 | Docker testing only |
| RPM | fedor | 8443 | Package testing only |

### URLs
- **netsuit DEV**: https://netsuit.lan.pew.pet:8443
- pve DEB: https://pve:8445
- pve Docker: https://pve:8444  
- fedor RPM: https://fedor:8443

### Login
- admin / changeme123

---

## API Client Pattern

```jsx
// ✅ CORRECT - apiClient returns parsed JSON
const response = await apiClient.get('/certificates')
const certs = response.data

// ❌ WRONG - no double .data
const certs = response.data.data
```

---

## Notifications

```jsx
const { showError, showSuccess } = useNotification()

// ✅ CORRECT
showSuccess('Certificate created')
showError('Failed to create')

// ❌ WRONG - showNotification doesn't exist
showNotification('error', 'msg')
```

---

## Test Commands

```bash
cd /root/ucm-src/frontend && npm test        # Unit tests
cd /root/ucm-src/frontend && npm run test:e2e # E2E tests
cd /root/ucm-src/backend && pytest            # Backend tests
```

---

## Working Method

1. **Read plan.md** before starting work
2. **Never guess** - search code, verify, then ask if unsure
3. **Multi-distro** - support deb, rpm, docker
4. **Test on all platforms** before saying "done"
5. **Push to main AND 2.1.0-dev**

### ⚠️ Instructions Files
- **Keep instructions LOCAL only** - never commit to git
- Instructions in: `/root/.copilot/copilot-instructions.md`
- Never create CLAUDE.md or similar in repository

---

## Common Gotchas

### Double API prefix
```jsx
// ✅ apiClient already has /api/v2 base
apiClient.get('/certificates')

// ❌ WRONG
apiClient.get('/api/v2/certificates')
```

### Icon colors - use CSS classes
```jsx
// ✅ CORRECT
<div className="icon-bg-orange">

// ❌ WRONG
<div style={{background: 'orange'}}>
```

### FormModal - use form data
```jsx
// FormModal collects form data via FormData API
<FormModal onSubmit={(data) => handleSubmit(data)}>
  <Input name="field1" />
</FormModal>
```

### FileUpload - two modes
```jsx
// Mode 1: Immediate callback (for modals)
<FileUpload onFileSelect={(file) => setFile(file)} />

// Mode 2: With upload button
<FileUpload onUpload={(files) => uploadFiles(files)} />
```

---

## Screenshots

```bash
python3 /root/.copilot/skills/ui-audit/audit_screenshots_v2.py [page] [options]

# Examples
python3 audit_screenshots_v2.py dashboard --mobile
python3 audit_screenshots_v2.py certificates --select
python3 audit_screenshots_v2.py --full-audit
```

---

## Database

- Path: `/opt/ucm/data/ucm.db`
- **⚠️ NEVER modify without explicit permission**
- Always backup first: `cp /opt/ucm/data/ucm.db /opt/ucm/data/ucm.db.bak`

### Migrations
- Located in: `/root/ucm-src/backend/migrations/`
- Auto-run at startup (check `migration_version` in `system_config`)
- Format: `NNN_description.py` with `upgrade(conn)` and `downgrade(conn)` functions
- Use `CREATE TABLE IF NOT EXISTS` for idempotency

```python
# Example migration (backend/migrations/010_create_acme_client_tables.py)
MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS my_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

def upgrade(conn):
    conn.executescript(MIGRATION_SQL)
    conn.commit()

def downgrade(conn):
    conn.execute("DROP TABLE IF EXISTS my_table")
    conn.commit()
```

---

## Logs

```bash
# Local - Application logs (CHECK THIS FIRST for errors)
tail -50 /var/log/ucm/ucm.log

# Local - Systemd journal
journalctl -u ucm --no-pager -n 50

# Remote
ssh pve "tail -50 /var/log/ucm/ucm.log"
ssh pve "journalctl -u ucm --no-pager -n 50"
ssh fedor "tail -50 /var/log/ucm/ucm.log"
ssh fedor "journalctl -u ucm --no-pager -n 50"

# Docker
ssh pve "docker logs \$(docker ps -q --filter 'publish=8444') --tail 50"
```

### ⚠️ ALWAYS check `/var/log/ucm/ucm.log` for Python errors!
