# Certificate Discovery Implementation

## Summary

The Certificate Discovery feature has been successfully implemented in the `feature/certificate-discovery` branch. This feature allows UCM to scan network targets for TLS certificates and import them into the system.

## Files Created

### Backend
1. **`backend/models/discovered_certificate.py`**
   - Model for storing discovered certificates
   - Tracks target, certificate details, status (known/unknown)
   - Relationship to existing UCM certificates

2. **`backend/services/discovery_service.py`**
   - Core discovery logic
   - TLS certificate extraction using Python's `ssl` module
   - Concurrent scanning with ThreadPoolExecutor
   - Subnet scanning using `ipaddress` module
   - Import functionality to add certificates to UCM

3. **`backend/api/v2/discovery.py`**
   - REST API endpoints for discovery
   - `/discovery/scan` - Scan multiple targets
   - `/discovery/scan-subnet` - Scan a subnet
   - `/discovery/import` - Import discovered certificates
   - `/discovery/history` - Get discovery history
   - `/discovery/unknown` - Get unknown certificates
   - `/discovery/expired` - Get expired certificates

4. **`backend/migrations/040_create_discovered_certificate_table.py`**
   - Database migration for the discovered_certificate table
   - Creates table with proper indexes and constraints

### Frontend
1. **`frontend/src/services/discovery.service.js`**
   - Frontend service for API communication
   - Standardized methods matching backend endpoints

2. **`frontend/src/pages/DiscoveryPage.jsx`**
   - Complete UI for certificate discovery
   - 5 tabs: Scan, Results, History, Unknown, Expired
   - Scan configuration (targets or subnet)
   - Import functionality
   - Statistics dashboard
   - Responsive design

3. **Updated `frontend/src/services/index.js`**
   - Exports discoveryService for use throughout the app

### Updated Files
1. **`backend/models/__init__.py`**
   - Added DiscoveredCertificate to imports and __all__

2. **`backend/api/v2/__init__.py`**
   - Registered discovery blueprint

## Features Implemented

### Backend
- ✅ TLS certificate extraction from network targets
- ✅ Concurrent scanning (configurable worker count)
- ✅ Subnet scanning with CIDR notation
- ✅ Certificate fingerprinting (SHA-256)
- ✅ Duplicate detection
- ✅ Import to UCM with status tracking
- ✅ History tracking
- ✅ Expired certificate detection

### Frontend
- ✅ Scan configuration UI
- ✅ Target-based scanning
- ✅ Subnet-based scanning
- ✅ Results display with certificate details
- ✅ Import functionality
- ✅ History view
- ✅ Unknown certificates view
- ✅ Expired certificates view
- ✅ Statistics dashboard
- ✅ Responsive design
- ✅ Internationalization support
- ✅ RBAC integration

## Usage

### Backend API

#### Scan Targets
```bash
POST /api/v2/discovery/scan
Content-Type: application/json

{
  "targets": ["example.com", "192.168.1.1"],
  "ports": [443, 8443]
}
```

#### Scan Subnet
```bash
POST /api/v2/discovery/scan-subnet
Content-Type: application/json

{
  "subnet": "192.168.1.0/24",
  "ports": [443, 8443]
}
```

#### Import Certificates
```bash
POST /api/v2/discovery/import
Content-Type: application/json

{
  "certificates": [
    {
      "target": "example.com:443",
      "certificate": "-----BEGIN CERTIFICATE-----...",
      "issuer": "CN=DigiCert...",
      "subject": "CN=example.com...",
      "serial": "0x123456789...",
      "not_before": "2024-01-01T00:00:00",
      "not_after": "2025-01-01T00:00:00",
      "fingerprint": "A1B2C3D4..."
    }
  ]
}
```

#### Get History
```bash
GET /api/v2/discovery/history?limit=100
```

#### Get Unknown Certificates
```bash
GET /api/v2/discovery/unknown
```

#### Get Expired Certificates
```bash
GET /api/v2/discovery/expired
```

### Frontend Usage

1. Navigate to the Discovery page in the UCM UI
2. Configure scan targets or subnet
3. Click "Scan" to start discovery
4. Review results and import certificates
5. Check history, unknown, and expired tabs

## Architecture

### Backend Architecture
```
User Request → API Endpoint → DiscoveryService → TLS Connection → Certificate Extraction → Database Storage
```

### Frontend Architecture
```
UI → DiscoveryService (frontend) → API Client → Backend API → DiscoveryService (backend) → Database
```

## Testing

### Backend Tests
```bash
cd /root/ucm-src/backend
pytest tests/test_discovery.py -v
```

### Frontend Tests
```bash
cd /root/ucm-src/frontend
npm test -- discovery
```

## Database Schema

```sql
CREATE TABLE discovered_certificate (
    id INTEGER PRIMARY KEY,
    target VARCHAR(1024) NOT NULL,
    certificate TEXT NOT NULL,
    issuer VARCHAR(1024),
    subject VARCHAR(1024),
    serial VARCHAR(64),
    not_before DATETIME,
    not_after DATETIME,
    fingerprint VARCHAR(64) UNIQUE,
    status VARCHAR(32) DEFAULT 'unknown',
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    ucm_certificate_id INTEGER,
    FOREIGN KEY (ucm_certificate_id) REFERENCES certificate(id) ON DELETE SET NULL
);

CREATE INDEX ix_discovered_certificate_target ON discovered_certificate(target);
CREATE INDEX ix_discovered_certificate_serial ON discovered_certificate(serial);
CREATE INDEX ix_discovered_certificate_status ON discovered_certificate(status);
CREATE INDEX ix_discovered_certificate_last_seen ON discovered_certificate(last_seen);
```

## Performance Considerations

- **Concurrent Scanning**: Uses ThreadPoolExecutor for parallel connections
- **Timeout Handling**: Configurable timeout to prevent hanging
- **Rate Limiting**: Not implemented (can be added if needed)
- **Memory Usage**: Certificates stored in database, not in memory

## Security Considerations

- **No Credential Storage**: Target credentials not stored
- **TLS Only**: Only scans TLS/SSL endpoints
- **Permission Required**: Requires `admin:system` permission
- **No Aggressive Scanning**: Respects timeout settings

## Future Enhancements

1. **Scheduled Scans**: Add to scheduler for regular discovery
2. **Alerts**: Notify when unknown certificates are found
3. **Export**: Export discovery results to CSV/JSON
4. **Advanced Filtering**: Filter by issuer, subject, expiry date
5. **Visualization**: Network map of discovered certificates
6. **Integration**: Integrate with vulnerability scanning

## Migration Path

1. Apply database migration:
   ```bash
   cd /root/ucm-src/backend
   flask db upgrade
   ```

2. Restart UCM service:
   ```bash
   sudo systemctl restart ucm
   ```

3. Access Discovery page in UI

## Troubleshooting

### Common Issues

1. **Connection Timeout**: Increase timeout in DiscoveryService
2. **Permission Denied**: Ensure `admin:system` permission
3. **Certificate Parse Errors**: Check certificate format
4. **Database Errors**: Verify migration was applied

### Debugging

```bash
# Check logs
cd /root/ucm-src/backend
python3 -c "from services.discovery_service import DiscoveryService; ds = DiscoveryService(); cert = ds.scan_target('example.com'); print(cert)"

# Check API
curl -X POST http://localhost:8443/api/v2/discovery/scan \
  -H "Content-Type: application/json" \
  -d '{"targets": ["example.com"]}'
```

## Conclusion

The Certificate Discovery feature is fully implemented and ready for testing. It follows UCM's existing patterns and architecture, making it maintainable and consistent with the rest of the codebase.
