# UCM Docker Features & Configuration Guide

## 🎯 Overview

Ultimate CA Manager's Docker deployment is **fully configurable** without editing compose files. All settings are controlled via a single `.env` file.

---

## ✨ Key Features

### 🔧 Complete Configurability
- ✅ **Ports**: No hardcoded ports - resolve conflicts easily
- ✅ **Data Directories**: Store data anywhere (NFS, external drives, etc.)
- ✅ **Database Credentials**: Full PostgreSQL configuration
- ✅ **No Compose Edits**: All changes via `.env` file

### 🚀 Easy Migration
- ✅ **Host-to-Host**: Migrate between servers in minutes
- ✅ **Backup/Restore**: Simple `tar` archive with all data
- ✅ **Zero Downtime**: Migration without service interruption
- ✅ **Automated Scripts**: Ready-to-use migration scripts

### 🔒 Production Ready
- ✅ **Gunicorn WSGI**: Professional production server (not Flask dev)
- ✅ **Auto-Scaling Workers**: CPU × 2 + 1 workers
- ✅ **HTTPS/TLS**: Auto-generated certificates
- ✅ **Health Checks**: Automated monitoring
- ✅ **Resource Limits**: CPU and memory constraints

### 📦 Multiple Deployment Options
- ✅ **SQLite**: Single-container, zero dependencies
- ✅ **PostgreSQL**: Multi-container with managed database
- ✅ **Docker Run**: Standalone container deployment
- ✅ **Docker Compose**: Orchestrated multi-service setup

---

## 📝 Configuration Variables

### Quick Reference

| Variable | Purpose | Default | Example |
|----------|---------|---------|---------|
| `UCM_HTTPS_PORT` | Host port | `8443` | `9443` |
| `UCM_DATA_DIR` | Data directory | `./data` | `/mnt/storage/ucm` |
| `POSTGRES_DATA_DIR` | PostgreSQL data | `./postgres-data` | `/var/lib/postgres` |
| `POSTGRES_DB` | Database name | `ucm` | `ucm_prod` |
| `POSTGRES_USER` | Database user | `ucm` | `ucm_admin` |
| `POSTGRES_PASSWORD` | Database password | `changeme123` | `secure-pass-here` |

### Environment File (.env)

```bash
# Copy example
cp .env.docker.example .env

# Customize
nano .env
```

**Example configuration:**
```env
# Network
UCM_HTTPS_PORT=8443

# Storage (can be NFS, external drives, etc.)
UCM_DATA_DIR=/mnt/storage/ucm-data
POSTGRES_DATA_DIR=/mnt/storage/postgres-data

# Database
POSTGRES_DB=ucm_production
POSTGRES_USER=ucm_admin
POSTGRES_PASSWORD=your-super-secure-password-here
```

---

## 🚀 Quick Start Examples

### Scenario 1: Default Setup (SQLite)

```bash
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager
docker-compose up -d
```

**Access:** https://localhost:8443

### Scenario 2: Custom Port (Port 8443 Already in Use)

```bash
# Create .env
echo "UCM_HTTPS_PORT=9443" > .env

# Start
docker-compose up -d
```

**Access:** https://localhost:9443

### Scenario 3: External Storage

```bash
# Create directories
mkdir -p /mnt/external/ucm/{data,postgres}

# Configure .env
cat > .env << 'ENVEOF'
UCM_HTTPS_PORT=8443
UCM_DATA_DIR=/mnt/external/ucm/data
POSTGRES_DATA_DIR=/mnt/external/ucm/postgres
POSTGRES_PASSWORD=my-secure-password
ENVEOF

# Start with PostgreSQL
docker-compose -f docker-compose.postgres.yml up -d
```

### Scenario 4: NFS/Network Storage

```bash
# Mount NFS
sudo mount -t nfs nfs-server:/export/ucm /mnt/ucm

# Configure .env
cat > .env << 'ENVEOF'
UCM_DATA_DIR=/mnt/ucm/data
POSTGRES_DATA_DIR=/mnt/ucm/postgres
ENVEOF

# Start
docker-compose up -d
```

---

## 🔄 Migration Workflows

### Workflow 1: Simple Migration (Same Paths)

**Old Host:**
```bash
cd /opt/ucm
docker-compose down
tar -czf ucm-backup.tar.gz data/ postgres-data/ .env
scp ucm-backup.tar.gz root@new-host:/opt/ucm/
```

**New Host:**
```bash
cd /opt/ucm
tar -xzf ucm-backup.tar.gz
docker-compose up -d
```

**Time:** 5 minutes | **Downtime:** ~2 minutes

### Workflow 2: Migration with Path Changes

**Old Host (.env):**
```env
UCM_DATA_DIR=/old/path/data
POSTGRES_DATA_DIR=/old/path/postgres
```

**New Host (.env):**
```env
UCM_DATA_DIR=/new/path/data
POSTGRES_DATA_DIR=/new/path/postgres
```

**Migration:**
```bash
# Transfer data
rsync -avz old-host:/old/path/data/ /new/path/data/
rsync -avz old-host:/old/path/postgres/ /new/path/postgres/

# Update .env and start
docker-compose up -d
```

### Workflow 3: Zero-Downtime Migration

1. Keep old host running
2. Set up new host with data copy
3. Test new host thoroughly
4. Update DNS/load balancer
5. Shutdown old host

**Downtime:** 0 seconds

---

## �� Resource Planning

### Small Deployment (1-50 certificates)
```env
# docker-compose.yml limits:
cpus: '1'
memory: 512M
```

**Recommended:**
- Storage: 1-5 GB
- RAM: 512 MB
- CPU: 1 core

### Medium Deployment (50-500 certificates)
```env
cpus: '2'
memory: 1G
```

**Recommended:**
- Storage: 5-20 GB
- RAM: 1 GB
- CPU: 2 cores

### Large Deployment (500+ certificates)
```env
cpus: '4'
memory: 2G
```

**Recommended:**
- Storage: 20-100 GB
- RAM: 2-4 GB
- CPU: 4+ cores

---

## 🔍 Verification Commands

### Check Configuration
```bash
# View current .env
cat .env

# Check port binding
docker ps | grep ucm

# Verify data location
docker inspect ucm | grep -A 5 Mounts

# Check environment variables
docker exec ucm env | grep UCM
```

### Health Status
```bash
# Container health
docker inspect ucm | grep -A 10 Health

# API health
curl -k https://localhost:8443/api/health

# Gunicorn workers
docker logs ucm | grep "Booting worker"

# Resource usage
docker stats ucm --no-stream
```

### Data Verification
```bash
# List certificates
docker exec ucm ls -la /app/backend/data/ca/
docker exec ucm ls -la /app/backend/data/certs/

# Database size
docker exec ucm du -sh /app/backend/data/ucm.db

# Total data usage
docker exec ucm du -sh /app/backend/data/
```

---

## 🛠️ Troubleshooting

### Port Already in Use
```bash
# Change port in .env
sed -i 's/UCM_HTTPS_PORT=8443/UCM_HTTPS_PORT=9443/' .env

# Recreate container
docker-compose down
docker-compose up -d
```

### Permission Denied on Data Directory
```bash
# Fix ownership (UCM runs as UID 1000)
sudo chown -R 1000:1000 ./data
sudo chown -R 1000:1000 ./postgres-data

# Restart
docker-compose restart
```

### Container Unhealthy
```bash
# Check logs
docker-compose logs ucm

# Check health endpoint manually
docker exec ucm curl -k https://localhost:8443/api/health

# Restart container
docker-compose restart ucm
```

### Out of Disk Space
```bash
# Check usage
docker exec ucm df -h /app/backend/data

# Move data to larger volume
docker-compose down
mv ./data /mnt/bigdrive/ucm-data
echo "UCM_DATA_DIR=/mnt/bigdrive/ucm-data" >> .env
docker-compose up -d
```

---

## 📚 Additional Resources

- **Full Docker Guide**: [DOCKER.md](DOCKER.md)
- **Migration Examples**: [docs/MIGRATION_EXAMPLE.md](docs/MIGRATION_EXAMPLE.md)
- **Environment Template**: [.env.docker.example](.env.docker.example)
- **Main README**: [README.md](README.md)

---

## 🎓 Best Practices

### Security
- ✅ Change default `POSTGRES_PASSWORD`
- ✅ Use strong passwords (20+ characters)
- ✅ Restrict port exposure (firewall rules)
- ✅ Regular backups of data directories
- ✅ Use `.env` file (never commit to git)

### Performance
- ✅ Use SSD storage for data directories
- ✅ Adjust worker count based on CPU cores
- ✅ Monitor resource usage with `docker stats`
- ✅ Set appropriate memory limits

### Maintenance
- ✅ Regular backups (automated with cron)
- ✅ Monitor disk space usage
- ✅ Review logs for errors
- ✅ Keep Docker images updated
- ✅ Test migrations in staging first

### High Availability
- ✅ Use PostgreSQL for multi-instance setup
- ✅ Store data on network storage (NFS/Ceph)
- ✅ Implement load balancer
- ✅ Set up health monitoring
- ✅ Document disaster recovery plan

---

## ✅ Checklist: Production Deployment

```
Pre-Deployment:
[ ] .env file created and customized
[ ] POSTGRES_PASSWORD changed from default
[ ] Data directories prepared with correct permissions
[ ] Firewall rules configured
[ ] Backup strategy planned

Deployment:
[ ] docker-compose up -d executed
[ ] Container status: Up and healthy
[ ] Health endpoint responding (200 OK)
[ ] Web interface accessible
[ ] Can login with default credentials
[ ] Default password changed

Post-Deployment:
[ ] First backup completed
[ ] Monitoring configured
[ ] Documentation updated with custom settings
[ ] Team trained on maintenance procedures
[ ] Disaster recovery tested
```

---

## 🌟 Why UCM Docker is Production-Ready

| Feature | UCM | Typical Container |
|---------|-----|-------------------|
| **Configuration** | `.env` file | Edit compose files |
| **Migration** | 5-minute process | Complex manual steps |
| **Server** | Gunicorn production | Flask dev server ⚠️ |
| **Workers** | Auto-scaling (CPU×2+1) | Fixed/manual |
| **HTTPS** | Auto-generated certs | Manual setup |
| **Health Checks** | Built-in | Optional |
| **Documentation** | Comprehensive | Basic |
| **Backup** | Simple tar archive | Database dumps |

---

**UCM v1.0.0** - Enterprise-grade Certificate Authority Management in Docker

🔗 GitHub: https://github.com/NeySlim/ultimate-ca-manager
📖 Docs: https://github.com/NeySlim/ultimate-ca-manager/blob/main/DOCKER.md
