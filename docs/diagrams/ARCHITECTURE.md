# UCM Architecture Diagrams

This document contains Mermaid diagrams that are automatically rendered on GitHub.

## System Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        A[Web Browser]
        B[Mobile Device]
        C[IoT Device]
        D[Network Equipment]
    end
    
    subgraph "UCM Application"
        E[HTTPS/TLS<br/>Port 8443]
        F[Gunicorn WSGI<br/>17 Workers]
        G[Flask Application]
        H[REST API]
        I[SCEP Server<br/>RFC 8894]
        J[OCSP Responder<br/>RFC 6960]
    end
    
    subgraph "Business Logic"
        K[CA Manager]
        L[Certificate Service]
        M[User Management]
        N[Authentication<br/>JWT]
    end
    
    subgraph "Data Layer"
        O[(SQLite/PostgreSQL<br/>Database)]
        P[File Storage<br/>Certificates & Keys]
    end
    
    A -->|HTTPS| E
    B -->|SCEP Enrollment| I
    C -->|SCEP Enrollment| I
    D -->|OCSP Check| J
    
    E --> F
    F --> G
    G --> H
    G --> I
    G --> J
    
    H --> K
    H --> L
    H --> M
    I --> L
    J --> L
    
    M --> N
    K --> O
    L --> O
    L --> P
    M --> O
    
    style E fill:#2196F3,stroke:#1976D2,stroke-width:2px,color:#fff
    style F fill:#4CAF50,stroke:#388E3C,stroke-width:2px,color:#fff
    style O fill:#FF9800,stroke:#F57C00,stroke-width:2px,color:#fff
    style P fill:#FF9800,stroke:#F57C00,stroke-width:2px,color:#fff
```

## Certificate Issuance Flow

```mermaid
sequenceDiagram
    participant User
    participant WebUI
    participant API
    participant CertService
    participant CAManager
    participant Database
    participant FileSystem
    
    User->>WebUI: Request New Certificate
    WebUI->>API: POST /api/certificates
    API->>API: Validate JWT Token
    API->>CertService: create_certificate()
    CertService->>CAManager: get_ca(ca_id)
    CAManager->>Database: SELECT ca_data
    Database-->>CAManager: CA Certificate & Key
    CAManager-->>CertService: CA Object
    CertService->>CertService: Generate Key Pair
    CertService->>CertService: Create CSR
    CertService->>CertService: Sign with CA
    CertService->>Database: INSERT certificate
    CertService->>FileSystem: Save cert.pem
    CertService->>FileSystem: Save key.pem
    CertService-->>API: Certificate Object
    API-->>WebUI: JSON Response
    WebUI-->>User: Display Success + Download
```

## SCEP Enrollment Flow

```mermaid
sequenceDiagram
    participant Device
    participant SCEP
    participant CA
    participant DB
    
    Device->>SCEP: GetCACert
    SCEP->>CA: get_ca_certificate()
    CA-->>SCEP: CA Certificate
    SCEP-->>Device: CA Cert (PEM)
    
    Device->>Device: Generate Key Pair
    Device->>Device: Create CSR
    Device->>Device: Encrypt with CA key
    
    Device->>SCEP: PKIOperation (PKCS#7)
    SCEP->>SCEP: Verify Challenge
    SCEP->>CA: sign_csr()
    CA->>DB: INSERT certificate
    CA-->>SCEP: Signed Certificate
    SCEP-->>Device: PKCS#7 Response
    
    Device->>Device: Install Certificate
```

## CA Hierarchy

```mermaid
graph TD
    A[Root CA<br/>Valid: 10 years]
    B[Intermediate CA 1<br/>Valid: 5 years]
    C[Intermediate CA 2<br/>Valid: 5 years]
    D[Server Cert]
    E[Client Cert]
    F[Device Cert]
    
    A -->|Signs| B
    A -->|Signs| C
    B -->|Issues| D
    B -->|Issues| E
    C -->|Issues| F
    
    style A fill:#E91E63,stroke:#C2185B,stroke-width:3px,color:#fff
    style B fill:#2196F3,stroke:#1976D2,stroke-width:2px,color:#fff
    style C fill:#2196F3,stroke:#1976D2,stroke-width:2px,color:#fff
```

## Docker Deployment

```mermaid
graph LR
    A[Git Tag v1.0.x] -->|Triggers| B[GitHub Actions]
    B --> C[Release]
    B --> D[Docker Build]
    
    D --> E[Multi-arch<br/>amd64 + arm64]
    E --> F[Docker Hub]
    F --> G[neyslim/ucm]
    
    H[docker pull] --> G
    H --> I[Container Running]
```

---

**Note**: These diagrams render automatically on GitHub!
