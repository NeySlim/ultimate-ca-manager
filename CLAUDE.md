# UCM Project Instructions

## Repository

**Single repository**: `/root/ucm-src/` → `NeySlim/ultimate-ca-manager`

- **Branch main**: production releases
- **Branch 2.1.0-dev**: development
- **Pro repo archived**: All features merged into main

### ⚠️ CRITICAL
- **Code in**: `/root/ucm-src/`
- **Test on**: netsuit (local), pve (DEB:8445, Docker:8444), fedor (RPM:8443)
- **Never use**: `/root/ucm-src-pro/` (archived)

---

## Deployment

### Build Frontend
```bash
cd /root/ucm-src/frontend && npm run build
```

### Deploy to pve (DEB - port 8445)
```bash
ssh pve "rm -rf /opt/ucm/frontend/dist/*"
scp -rq /root/ucm-src/frontend/dist/* pve:/opt/ucm/frontend/dist/
ssh pve "systemctl restart ucm"
```

### Deploy to fedor (RPM - port 8443)
```bash
ssh fedor "rm -rf /opt/ucm/frontend/dist/*"
scp -rq /root/ucm-src/frontend/dist/* fedor:/opt/ucm/frontend/dist/
ssh fedor "systemctl restart ucm"
```

### Deploy to Docker (pve:8444)
```bash
CONTAINER_ID=$(ssh pve "docker ps -q --filter 'publish=8444'")
ssh pve "docker cp - $CONTAINER_ID:/app/frontend/" < <(cd /root/ucm-src/frontend && tar -cf - dist)
```

### Deploy Backend
```bash
scp -rq /root/ucm-src/backend/* pve:/opt/ucm/backend/
ssh pve "systemctl restart ucm"
```

---

## Git Workflow

```bash
cd /root/ucm-src

# Commit
git add -A && git commit -m "type(scope): message"

# Push to main AND dev
git push origin main
git push origin main:2.1.0-dev
```

---

## Test Environments

| Type | Host | Port | Version Check |
|------|------|------|---------------|
| DEB | pve | 8445 | `ssh pve "cat /opt/ucm/VERSION"` |
| Docker | pve | 8444 | Browser → About |
| RPM | fedor | 8443 | `ssh fedor "cat /opt/ucm/VERSION"` |

### URLs
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

- Path: `/opt/ucm/backend/ucm.db`
- **⚠️ NEVER modify without explicit permission**
- Always backup first: `cp ucm.db ucm.db.bak`

---

## Logs

```bash
# Local
journalctl -u ucm --no-pager -n 50

# Remote
ssh pve "journalctl -u ucm --no-pager -n 50"
ssh fedor "journalctl -u ucm --no-pager -n 50"

# Docker
ssh pve "docker logs \$(docker ps -q --filter 'publish=8444') --tail 50"
```
