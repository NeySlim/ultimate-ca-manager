# Certificates Module - Implementation Guide

## Overview

The Certificates module provides a comprehensive interface for managing digital certificates with a dense, technical aesthetic inspired by file managers. It includes a rich table view for listing certificates and detailed pages for viewing certificate information.

## Module Structure

```
modules/Certificates/
├── components/
│   ├── CertificateTable.jsx      # Rich table with filters
│   ├── CertificateTable.css      # Table styling
│   ├── CertificateListView.jsx   # Legacy list view
│   ├── CertificateGridView.jsx   # Legacy grid view
│   └── index.js                  # Component exports
├── pages/
│   ├── CertificatesListPage.jsx      # Main list page
│   ├── CertificatesListPage.css      # List page styling
│   ├── CertificateDetailPage.jsx     # Detail view page
│   ├── CertificateDetailPage.css     # Detail page styling
│   └── CertificatesPage.jsx          # Legacy page (deprecated)
├── services/
│   └── certificates.service.js   # API service with mock data
├── routes.jsx                    # Module routing configuration
└── README.md                     # This file
```

## Features

### Certificate List Page (`CertificatesListPage.jsx`)

Main interface for viewing all certificates with the following features:

**Toolbar Actions:**
- Create new certificate
- Import existing certificate
- Certificate count display

**Filtering & Search:**
- Full-text search (Common Name, Issuer, Serial)
- Status filter (Valid, Warning, Expired, Revoked)
- Certificate Authority filter
- Real-time result count

**Rich Table Columns:**
- **Status**: Color-coded badge (green/yellow/red/gray)
- **Common Name**: Primary identifier
- **Serial**: Abbreviated with monospace font + tooltip
- **Issuer**: Issuing CA
- **Issued**: Date issued
- **Expires**: Expiry date with critical warning icon
- **Algorithm**: Encryption algorithm used
- **Actions**: View, Download, Delete

**Row Actions:**
- Click row to view details
- Download certificate (PEM format)
- Delete certificate (with confirmation)
- View full details button

### Certificate Detail Page (`CertificateDetailPage.jsx`)

Comprehensive certificate information viewer with tabbed interface:

**Header Section:**
- Back button to certificate list
- Common Name and Status badge
- Download, Renew, and Revoke action buttons

**Tabs:**

1. **General Info**
   - Serial Number (with copy button)
   - Algorithm
   - Key Size
   - Version
   - Certificate Authority
   - Thumbprint (SHA-1)

2. **Subject**
   - Common Name (CN)
   - Organization (O)
   - Organizational Unit (OU)
   - Country (C)
   - State (ST)
   - Locality (L)
   - Alternative Names (SANs)

3. **Issuer**
   - Issuer Name
   - Organization
   - Country
   - Common Name

4. **Validity**
   - Issued On (full timestamp)
   - Expires On (full timestamp)
   - Validity Period (days)
   - Days Remaining

5. **Extensions**
   - All X.509 extensions listed
   - Critical flag indicators
   - Extension values

6. **PEM**
   - Full certificate PEM format
   - Read-only textarea
   - Copy button
   - Download button

## Routing

The module uses nested routing for navigation:

```javascript
// Module routes (routes.jsx)
/certificates/          → CertificatesListPage
/certificates/:id       → CertificateDetailPage
```

**Navigation:**
- List page header link to "Certificates"
- Click any row or "View Details" button to see detail page
- Back button in detail page returns to list

## Data Structure

### Certificate Object (Mock Data Example)

```javascript
{
  id: 1,
  name: 'api.example.com',
  commonName: 'api.example.com',
  serial: 'A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0',
  issuer: 'Example Root CA',
  issuedDate: '2024-05-15',
  expiryDate: '2025-05-15',
  algorithm: 'RSA 2048',
  keySize: 2048,
  version: 'v3',
  ca: 'Example Root CA',
  status: 'Valid',              // Valid, Warning, Expired, Revoked
  thumbprint: 'A1B2C3D4E5F6...',
  subject: {
    commonName: 'api.example.com',
    organization: 'Example Corp',
    unit: 'IT Department',
    country: 'US',
    state: 'California',
    locality: 'San Francisco',
    altNames: ['api.example.com', 'api-v2.example.com']
  },
  issuerDetails: {
    commonName: 'Example Root CA',
    organization: 'Example Corp',
    country: 'US'
  },
  extensions: [
    { name: 'Basic Constraints', value: 'CA:FALSE', critical: true },
    { name: 'Key Usage', value: 'digitalSignature, keyEncipherment', critical: true }
  ],
  pem: '-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----'
}
```

## Service Methods

All methods in `certificates.service.js`:

```javascript
// Get all certificates
const certs = await CertificateService.getAll()

// Get single certificate by ID
const cert = await CertificateService.getById(id)

// Get statistics
const stats = await CertificateService.getStats()

// Revoke certificate
await CertificateService.revoke(id)

// Renew certificate
await CertificateService.renew(id)

// Download certificate
await CertificateService.download(id)
```

**Mock Data Fallback:**
- If API fails, service automatically returns mock data
- 5 sample certificates included for development/testing
- Covers various statuses: Valid, Warning, Expired

## Styling & Theme

### Design Principles
- Dark theme (background: #1a1a1a)
- Dense, technical interface
- File manager aesthetic
- Monospace font for technical data (JetBrains Mono)

### Color Scheme
- **Valid**: Green (#51cf66)
- **Warning**: Yellow (#ffd43b)
- **Expired**: Red (#fa5252)
- **Revoked**: Gray (#868e96)
- **Text**: Light gray (#e0e0e0)
- **Borders**: Dark gray (#333)

### Component Libraries
- **UI Framework**: @mantine/core v8.3.12
- **Icons**: @phosphor-icons/react v2.1.10
- **Utilities**: clsx v2.1.1

## Usage Examples

### Importing Components

```javascript
// Import specific component
import CertificateTable from './components/CertificateTable';

// Import from index
import { CertificateTable } from './components';

// Import service
import { CertificateService } from './services/certificates.service';
```

### Using CertificateTable

```jsx
<CertificateTable
  data={certificates}
  onRowClick={(cert) => navigate(`/certificates/${cert.id}`)}
  onView={(cert) => handleView(cert)}
  onDownload={(cert) => handleDownload(cert)}
  onDelete={(cert) => handleDelete(cert)}
/>
```

### Loading Certificate Details

```jsx
useEffect(() => {
  const loadCertificate = async () => {
    try {
      const cert = await CertificateService.getById(id);
      setCertificate(cert);
    } catch (error) {
      console.error('Failed to load certificate', error);
    }
  };
  loadCertificate();
}, [id]);
```

## API Integration

The service is designed to integrate with a backend API:

```javascript
GET  /certificates              # List all certificates
GET  /certificates/:id          # Get certificate details
GET  /certificates/:id/download # Download certificate
POST /certificates/:id/revoke   # Revoke certificate
POST /certificates/:id/renew    # Renew certificate
```

Currently uses mock data fallback for development. Replace API calls once backend is available.

## Future Enhancements

- [ ] Import certificate modal with file upload
- [ ] Create certificate wizard
- [ ] Bulk actions (delete, export multiple)
- [ ] Certificate expiry notifications
- [ ] CSR generation interface
- [ ] Key pair management
- [ ] Certificate chain viewer
- [ ] Export to various formats (PKCS12, JKS, etc.)
- [ ] Search history/favorites
- [ ] Sorting by multiple columns
- [ ] Pagination for large certificate lists

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## Performance Notes

- Table virtualizes large lists for performance
- Monospace font rendering optimized with font-size 0.8rem for readability
- CSS smooth transitions for better UX
- Debounced search input

## Troubleshooting

### Build Errors
- Ensure all imports are correct
- Check @mantine/core version compatibility
- Verify CSS files are imported

### Runtime Errors
- Check browser console for detailed error messages
- Verify mock data structure matches expected format
- Ensure API endpoints are correctly configured

### Styling Issues
- Clear browser cache if styles don't update
- Check CSS file imports
- Verify Mantine theme configuration in core/theme/

## Contributing

When modifying this module:
1. Keep the dense, technical aesthetic
2. Use monospace font for technical data
3. Follow existing component patterns
4. Add appropriate TypeScript types when available
5. Update this documentation

## License

Same as parent project UCM Frontend
