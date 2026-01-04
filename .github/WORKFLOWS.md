# GitHub Actions Setup Guide

This document explains how to configure GitHub Actions workflows for automated builds, releases, and Docker Hub publishing.

## 🔐 Required Secrets

Configure these secrets in your GitHub repository:

**Settings → Secrets and variables → Actions → New repository secret**

### 1. DOCKERHUB_TOKEN

**Purpose**: Authenticate to Docker Hub for pushing images

**How to create**:
1. Log in to [Docker Hub](https://hub.docker.com)
2. Click on your username → Account Settings
3. Security → New Access Token
4. Name: `github-actions-ucm`
5. Permissions: Read, Write, Delete
6. Copy the token (you won't see it again!)
7. Add to GitHub: Name = `DOCKERHUB_TOKEN`, Value = `<token>`

### 2. GITHUB_TOKEN (Automatic)

**Purpose**: Create releases, update repository

**Status**: ✅ Automatically provided by GitHub Actions (no setup needed)

---

## 📋 Workflows Overview

### 1. Docker Build and Push (`docker-publish.yml`)

**Triggers**:
- Push tag matching `v*.*.*` (e.g., v1.0.1)
- Manual trigger via workflow_dispatch

**What it does**:
- Builds multi-arch Docker images (amd64, arm64)
- Pushes to Docker Hub: `neyslim/ultimate-ca-manager`
- Tags: version, major.minor, major, latest
- Updates Docker Hub description with DOCKERHUB_README.md

**Example tags created**:
```
neyslim/ultimate-ca-manager:1.0.1
neyslim/ultimate-ca-manager:1.0
neyslim/ultimate-ca-manager:1
neyslim/ultimate-ca-manager:latest
```

**Manual trigger**:
```bash
# Via GitHub UI: Actions → Docker Build and Push → Run workflow
# Or via gh CLI:
gh workflow run docker-publish.yml -f tag=custom-tag
```

### 2. Release Automation (`release.yml`)

**Triggers**:
- Push tag matching `v*.*.*`

**What it does**:
- Checks for `RELEASE_NOTES_v*.*.*.md` file
- If exists: Uses it as release description
- If not: Auto-generates changelog from commits
- Creates GitHub Release
- Marks as latest
- Creates discussion (optional)

**Release notes priority**:
1. `RELEASE_NOTES_v1.0.1.md` (if exists) ← Preferred
2. Auto-generated from git commits

### 3. CI - Build and Test (`ci.yml`)

**Triggers**:
- Push to main/develop branches
- Pull requests to main/develop
- Manual trigger

**Jobs**:
1. **Lint**: flake8 code quality checks
2. **Test**: Run pytest on Python 3.10, 3.11, 3.12
3. **Docker Build**: Test Docker image builds
4. **Security Scan**: Trivy vulnerability scanning

**Status badges** (add to README.md):
```markdown
[![CI](https://github.com/NeySlim/ultimate-ca-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/NeySlim/ultimate-ca-manager/actions/workflows/ci.yml)
```

---

## 🚀 Usage Examples

### Create a New Release

1. **Prepare release notes** (optional but recommended):
   ```bash
   # Create release notes file
   cat > RELEASE_NOTES_v1.0.2.md << 'EOF'
   # UCM v1.0.2 - Bug Fixes and Improvements
   
   ## What's New
   - Fixed certificate validation
   - Improved performance
   EOF
   
   git add RELEASE_NOTES_v1.0.2.md
   git commit -m "docs: Add v1.0.2 release notes"
   git push
   ```

2. **Create and push tag**:
   ```bash
   git tag -a v1.0.2 -m "UCM v1.0.2 - Bug Fixes and Improvements"
   git push origin v1.0.2
   ```

3. **Wait for automation**:
   - ✅ GitHub Release created automatically
   - ✅ Docker images built and pushed to Docker Hub
   - ✅ Multi-arch support (amd64, arm64)

4. **Verify**:
   - GitHub: https://github.com/NeySlim/ultimate-ca-manager/releases
   - Docker Hub: https://hub.docker.com/r/neyslim/ultimate-ca-manager

---

## 🔍 Monitoring Workflows

### Check workflow status

```bash
# Install GitHub CLI
gh auth login

# List workflow runs
gh run list

# Watch specific workflow
gh run watch

# View logs
gh run view --log
```

### GitHub UI

- Actions tab: https://github.com/NeySlim/ultimate-ca-manager/actions
- Docker Hub: https://hub.docker.com/r/neyslim/ultimate-ca-manager/tags

---

## 🛠️ Troubleshooting

### Docker Hub Push Failed

**Error**: `denied: requested access to the resource is denied`

**Solution**:
1. Verify DOCKERHUB_TOKEN is set correctly
2. Check token has Write permissions
3. Verify username in workflow: `DOCKERHUB_USERNAME: neyslim`

### Release Not Created

**Error**: Release not appearing after tag push

**Solution**:
1. Check tag format: must be `v*.*.*` (e.g., v1.0.1)
2. Check workflow run in Actions tab for errors
3. Verify GITHUB_TOKEN has `contents: write` permission (automatic)

---

## 🎯 Complete Release Checklist

```
Pre-release:
[ ] Code changes committed and pushed
[ ] Tests passing locally
[ ] RELEASE_NOTES_vX.Y.Z.md created (optional)
[ ] Version updated in relevant files

Release:
[ ] Create tag: git tag -a vX.Y.Z -m "message"
[ ] Push tag: git push origin vX.Y.Z

Post-release (automatic):
[ ] GitHub Release created
[ ] Docker images pushed to Docker Hub
[ ] Multi-arch images available (amd64, arm64)
[ ] Docker Hub description updated

Verification:
[ ] GitHub release exists
[ ] Docker Hub shows new tags
[ ] Images can be pulled: docker pull neyslim/ultimate-ca-manager:X.Y.Z
[ ] Release notes correct
```

---

**Last Updated**: 2026-01-04
