# UCM Terraform Provider

Terraform provider for managing PKI resources in Ultimate CA Manager.

## Installation

```hcl
terraform {
  required_providers {
    ucm = {
      source  = "local/ucm/ucm"
      version = "0.1.0"
    }
  }
}
```

## Configuration

```hcl
provider "ucm" {
  host     = "https://ucm.example.com:8443"
  api_key  = var.ucm_api_key
  insecure = false  # Skip TLS verification (not recommended)
}
```

## Resources

### ucm_ca

Manage Certificate Authorities.

```hcl
resource "ucm_ca" "root" {
  common_name  = "Example Root CA"
  organization = "Example Inc"
  country      = "US"
  key_type     = "RSA-4096"
  validity_days = 3650
}

resource "ucm_ca" "intermediate" {
  common_name  = "Example Intermediate CA"
  organization = "Example Inc"
  country      = "US"
  key_type     = "RSA-2048"
  validity_days = 1825
  parent_refid = ucm_ca.root.refid
}
```

### ucm_certificate

Manage certificates.

```hcl
resource "ucm_certificate" "web" {
  common_name   = "www.example.com"
  ca_refid      = ucm_ca.intermediate.refid
  key_type      = "RSA-2048"
  validity_days = 397
  
  san_dns = [
    "www.example.com",
    "example.com"
  ]
  
  san_ip = ["192.168.1.1"]
  
  key_usage = ["digitalSignature", "keyEncipherment"]
  extended_key_usage = ["serverAuth"]
}
```

### ucm_template

Manage certificate templates.

```hcl
resource "ucm_template" "webserver" {
  name          = "Web Server"
  template_type = "web_server"
  key_type      = "RSA-2048"
  validity_days = 397
  
  extensions = {
    key_usage          = ["digitalSignature", "keyEncipherment"]
    extended_key_usage = ["serverAuth"]
    basic_constraints  = { ca = false }
  }
}
```

## Data Sources

### ucm_ca

```hcl
data "ucm_ca" "root" {
  refid = "abc123"
}
```

### ucm_certificate

```hcl
data "ucm_certificate" "by_cn" {
  common_name = "www.example.com"
}
```

## Example: Complete PKI Setup

```hcl
# Root CA
resource "ucm_ca" "root" {
  common_name       = "ACME Root CA"
  organization      = "ACME Corp"
  organizational_unit = "PKI"
  country           = "US"
  state             = "California"
  locality          = "San Francisco"
  key_type          = "RSA-4096"
  validity_days     = 7300  # 20 years
}

# Issuing CA
resource "ucm_ca" "issuing" {
  common_name       = "ACME Issuing CA"
  organization      = "ACME Corp"
  key_type          = "RSA-2048"
  validity_days     = 1825  # 5 years
  parent_refid      = ucm_ca.root.refid
}

# Web server template
resource "ucm_template" "webserver" {
  name          = "TLS Web Server"
  template_type = "web_server"
  key_type      = "RSA-2048"
  validity_days = 397
}

# Production web certificate
resource "ucm_certificate" "prod_web" {
  common_name   = "app.acme.com"
  ca_refid      = ucm_ca.issuing.refid
  template_id   = ucm_template.webserver.id
  
  san_dns = [
    "app.acme.com",
    "www.acme.com"
  ]
}

# Export certificate for use
output "web_certificate" {
  value = ucm_certificate.prod_web.certificate_pem
}

output "web_private_key" {
  value     = ucm_certificate.prod_web.private_key_pem
  sensitive = true
}
```

## API Key Setup

Create an API key in UCM:

1. Go to Account → API Keys
2. Click "Create API Key"
3. Set name and permissions
4. Copy the key and store securely

```bash
export TF_VAR_ucm_api_key="ucm_xxx..."
```

## Development

The provider is written in Go using the Terraform Plugin SDK v2.

```bash
cd terraform-provider-ucm
go build -o terraform-provider-ucm
```

## Contributing

See CONTRIBUTING.md for development guidelines.
