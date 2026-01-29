# Documentation Cleanup Plan - v1.8.0

## 📋 Current State (Chaos!)

### Root Level Docs (17 files!)
- README.md (1KB) - OBSOLETE v1.0.0
- CHANGELOG.md (38KB) - Good, keep
- CHANGELOG_COMPLETE.md (19KB) - DUPLICATE, delete
- INSTALLATION.md (6KB) - Outdated
- DOCKER_QUICKSTART.md (7KB) - Good but needs update
- DOCKERHUB_README.md (8KB) - Good but needs update
- PACKAGE_INSTALL_GUIDE.md (8KB) - DUPLICATE of INSTALLATION
- RPM_INSTALL_GUIDE.md (9KB) - Should merge with install guide
- UPGRADE.md (7KB) - Good, keep
- RELEASE_NOTES_1.6.0.md (4KB) - OLD, archive
- RELEASE_NOTES_v1.7.5.md (5KB) - OLD, archive
- GITHUB_DESCRIPTION.md (2KB) - Internal, move to docs/
- ROADMAP_v1.8_ACME.md (13KB) - OLD planning doc, archive
- BUILD_CHECKLIST.md (5KB) - Dev doc, move to docs/dev/
- CODE_AUDIT_2026-01-09.md (5KB) - Dev doc, move to docs/dev/
- DOCKERFILE_NOTES.md (4KB) - Dev doc, move to docs/dev/
- RELEASE_READY.md (6KB) - Dev doc, move to docs/dev/

### Wiki (5 files in repo)
- Home.md, CA-Management.md, Certificate-Operations.md, CRL-CDP.md, Themes.md
- Should stay but not duplicate in main repo

### Docs Folder
- docs/UCM_ICON_SYSTEM_GUIDE.md - Dev doc

---

## 🎯 Proposed Structure

```
ucm-src/
├── README.md (NEW - Complete v1.8.0 overview)
├── CHANGELOG.md (Keep, maintain)
├── LICENSE (Keep)
├── docs/
│   ├── installation/
│   │   ├── README.md (Main install guide - Docker/DEB/RPM/Source)
│   │   ├── docker.md (Detailed Docker guide)
│   │   ├── debian-ubuntu.md (DEB installation)
│   │   ├── rhel-rocky-alma.md (RPM installation)
│   │   └── from-source.md (Manual installation)
│   ├── user-guide/
│   │   ├── quick-start.md
│   │   ├── first-steps.md
│   │   ├── ca-management.md
│   │   ├── certificates.md
│   │   ├── protocols/
│   │   │   ├── scep.md
│   │   │   ├── ocsp.md
│   │   │   ├── crl.md
│   │   │   └── acme.md
│   │   └── advanced/
│   │       ├── mtls.md
│   │       ├── webauthn.md
│   │       └── api.md
│   ├── administration/
│   │   ├── configuration.md
│   │   ├── user-management.md
│   │   ├── backup-restore.md
│   │   ├── monitoring.md
│   │   └── troubleshooting.md
│   ├── deployment/
│   │   ├── production.md
│   │   ├── docker-compose.md
│   │   ├── kubernetes.md (future)
│   │   └── reverse-proxy.md
│   ├── development/
│   │   ├── architecture.md
│   │   ├── building.md
│   │   ├── contributing.md
│   │   ├── icon-system.md
│   │   └── testing.md
│   └── archive/
│       ├── release-notes-1.6.0.md
│       ├── release-notes-1.7.5.md
│       └── roadmaps/
│           └── v1.8-acme.md
└── wiki/ (GitHub Wiki repo - keep synced)
    └── (mirror of docs/user-guide/)
```

---

## 🔄 Migration Actions

### Phase 1: Update Core Files
- [ ] README.md - Complete rewrite v1.8.0
- [ ] DOCKERHUB_README.md - Update to v1.8.0
- [ ] CHANGELOG.md - Add v1.8.0-beta entries

### Phase 2: Create docs/ Structure
- [ ] mkdir -p docs/{installation,user-guide,administration,deployment,development,archive}
- [ ] Consolidate installation guides
- [ ] Move user guides
- [ ] Move admin guides
- [ ] Move dev docs

### Phase 3: Delete Duplicates/Obsolete
- [ ] Delete CHANGELOG_COMPLETE.md
- [ ] Delete PACKAGE_INSTALL_GUIDE.md
- [ ] Archive RELEASE_NOTES_*.md
- [ ] Archive ROADMAP_*.md
- [ ] Delete BUILD_CHECKLIST.md (or move to dev)
- [ ] Delete CODE_AUDIT_*.md (or move to dev)
- [ ] Delete DOCKERFILE_NOTES.md (or move to dev)
- [ ] Delete RELEASE_READY.md (or move to dev)
- [ ] Delete RPM_INSTALL_GUIDE.md (merge into unified guide)
- [ ] Delete INSTALLATION.md (replace with docs/installation/README.md)

### Phase 4: Wiki Sync
- [ ] Keep wiki/ folder as submodu or reference
- [ ] Add sync script to keep docs/ and wiki/ aligned
- [ ] Update wiki with links to main repo docs

---

## 📊 Before/After

### Before: 17+ scattered files, duplicates, outdated
### After: Organized docs/ structure, single source of truth

---

## ✅ Benefits

1. **Single Source of Truth** - No more duplicates
2. **Easy to Find** - Logical folder structure
3. **Easy to Maintain** - One place to update
4. **Version Controlled** - All in git
5. **Professional** - Standard docs/ structure
6. **CI/CD Ready** - Can auto-generate wiki from docs/

