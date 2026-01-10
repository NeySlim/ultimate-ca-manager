# Contributing

Thank you for considering contributing to Ultimate CA Manager v1.8.2! This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting](#issue-reporting)
- [Documentation](#documentation)

## Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inclusive environment for all contributors, regardless of background or experience level.

### Expected Behavior

- Be respectful and professional
- Accept constructive criticism gracefully
- Focus on what's best for the project
- Show empathy towards other community members

### Unacceptable Behavior

- Harassment or discrimination
- Trolling or insulting comments
- Publishing others' private information
- Any conduct inappropriate for a professional setting

## Getting Started

### Prerequisites

**Required:**
- Git
- Python 3.8+
- Basic understanding of Flask
- Familiarity with X.509 certificates and PKI concepts

**Recommended:**
- Experience with SQLAlchemy
- Knowledge of cryptography basics
- Understanding of ACME/SCEP protocols

### Fork and Clone

```bash
# Fork the repository on GitHub
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/ultimate-ca-manager.git
cd ultimate-ca-manager

# Add upstream remote
git remote add upstream https://github.com/fabriziosalmi/ultimate-ca-manager.git

# Verify remotes
git remote -v
```

## Development Setup

### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows
```

### 2. Install Dependencies

```bash
# Install in development mode
pip install -e .

# Install development dependencies
pip install -r requirements-dev.txt
```

**requirements-dev.txt:**
```
pytest>=7.4.0
pytest-flask>=1.2.0
pytest-cov>=4.1.0
black>=23.7.0
flake8>=6.1.0
isort>=5.12.0
mypy>=1.5.0
pre-commit>=3.3.0
```

### 3. Initialize Database

```bash
# Initialize development database
flask db upgrade

# Create test admin user
flask create-admin --username dev --password dev123 --email dev@localhost
```

### 4. Run Development Server

```bash
export FLASK_ENV=development
export FLASK_DEBUG=1
flask run
```

**Access:** http://localhost:5000

### 5. Install Pre-commit Hooks

```bash
pre-commit install
```

**Pre-commit config (`.pre-commit-config.yaml`):**
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.7.0
    hooks:
      - id: black
        language_version: python3.10

  - repo: https://github.com/pycqa/flake8
    rev: 6.1.0
    hooks:
      - id: flake8
        args: ['--max-line-length=100', '--ignore=E203,W503']

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
```

## How to Contribute

### Types of Contributions

**Bug Fixes:**
- Fix reported issues
- Add regression tests
- Update documentation

**Features:**
- Implement new functionality
- Add comprehensive tests
- Update user documentation

**Documentation:**
- Improve existing docs
- Add examples
- Fix typos

**Testing:**
- Increase test coverage
- Add integration tests
- Improve test reliability

### Contribution Workflow

1. **Check Existing Issues**
   - Search for related issues
   - Comment if you plan to work on it
   - Ask questions if unclear

2. **Create Issue (if needed)**
   - Describe the problem/feature
   - Provide examples
   - Wait for discussion/approval

3. **Create Branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/bug-description
   ```

4. **Make Changes**
   - Follow coding standards
   - Write tests
   - Update documentation

5. **Test Locally**
   ```bash
   # Run tests
   pytest tests/
   
   # Check code quality
   black app/ tests/
   flake8 app/ tests/
   isort app/ tests/
   ```

6. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   ```

7. **Push to Fork**
   ```bash
   git push origin feature/your-feature-name
   ```

8. **Create Pull Request**
   - Open PR on GitHub
   - Describe changes
   - Reference related issues

## Coding Standards

### Python Style Guide

**Follow PEP 8 with modifications:**
- Line length: 100 characters (not 79)
- Use `black` for formatting
- Use `isort` for import sorting

**Naming Conventions:**
```python
# Variables and functions: snake_case
user_count = 10
def get_certificate():
    pass

# Classes: PascalCase
class CertificateManager:
    pass

# Constants: UPPER_SNAKE_CASE
MAX_VALIDITY_DAYS = 3650

# Private methods: _leading_underscore
def _internal_method():
    pass
```

### Code Organization

**Module Structure:**
```python
"""Module docstring describing purpose."""

# Standard library imports
import os
import sys

# Third-party imports
from flask import Flask
from cryptography import x509

# Local imports
from app.models import Certificate
from app.utils import validators

# Constants
DEFAULT_KEY_SIZE = 4096

# Functions/Classes
def create_certificate():
    """Function docstring."""
    pass
```

### Documentation

**Docstrings (Google Style):**
```python
def create_certificate(common_name, validity_days=365):
    """Create a new X.509 certificate.
    
    Args:
        common_name (str): Certificate common name
        validity_days (int, optional): Validity period in days. Defaults to 365.
    
    Returns:
        Certificate: The created certificate object
    
    Raises:
        ValueError: If common_name is empty
        CryptoError: If certificate generation fails
    
    Example:
        >>> cert = create_certificate("example.com", validity_days=730)
        >>> print(cert.serial_number)
        01
    """
    pass
```

### Error Handling

```python
# Good: Specific exceptions
try:
    cert = create_certificate(cn)
except ValueError as e:
    logger.error(f"Invalid input: {e}")
    raise
except CryptoError as e:
    logger.error(f"Crypto operation failed: {e}")
    return None

# Bad: Bare except
try:
    cert = create_certificate(cn)
except:  # Don't do this
    pass
```

### Logging

```python
import logging

logger = logging.getLogger(__name__)

# Use appropriate levels
logger.debug("Detailed information for debugging")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error occurred")
logger.critical("Critical error")

# Include context
logger.info(f"Created certificate for {common_name}")
logger.error(f"Failed to revoke certificate {serial}: {error}")
```

## Testing

### Test Structure

```
tests/
├── conftest.py              # Pytest fixtures
├── unit/                    # Unit tests
│   ├── test_models.py
│   ├── test_ca_engine.py
│   └── test_crypto.py
├── integration/             # Integration tests
│   ├── test_api.py
│   ├── test_acme.py
│   └── test_scep.py
└── functional/              # End-to-end tests
    └── test_workflows.py
```

### Writing Tests

**Unit Test Example:**
```python
import pytest
from app.ca.engine import CAEngine

class TestCAEngine:
    def test_create_certificate(self, ca_engine):
        """Test certificate creation."""
        cert = ca_engine.create_certificate(
            common_name="test.example.com",
            validity_days=365
        )
        
        assert cert is not None
        assert cert.common_name == "test.example.com"
        assert cert.is_valid()
    
    def test_create_certificate_invalid_cn(self, ca_engine):
        """Test certificate creation with invalid CN."""
        with pytest.raises(ValueError):
            ca_engine.create_certificate(
                common_name="",
                validity_days=365
            )
```

**Integration Test Example:**
```python
def test_api_create_certificate(client, auth_token):
    """Test certificate creation via API."""
    response = client.post(
        '/api/certificates',
        headers={'Authorization': f'Bearer {auth_token}'},
        json={
            'common_name': 'api-test.example.com',
            'type': 'server',
            'validity_days': 365
        }
    )
    
    assert response.status_code == 201
    data = response.get_json()
    assert 'certificate' in data
    assert data['common_name'] == 'api-test.example.com'
```

### Test Fixtures (conftest.py)

```python
import pytest
from app import create_app
from app.models import db

@pytest.fixture
def app():
    """Create application for testing."""
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()

@pytest.fixture
def ca_engine(app):
    """Create CA engine instance."""
    from app.ca.engine import CAEngine
    return CAEngine()
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_ca_engine.py

# Run specific test
pytest tests/unit/test_ca_engine.py::TestCAEngine::test_create_certificate

# Run with verbose output
pytest -v

# Run and stop on first failure
pytest -x
```

### Test Coverage

**Minimum Requirements:**
- Overall coverage: 80%
- New code coverage: 90%
- Critical paths: 100%

**Check Coverage:**
```bash
pytest --cov=app --cov-report=term-missing
```

## Pull Request Process

### Before Submitting

**Checklist:**
- [ ] Code follows style guide
- [ ] Tests added/updated
- [ ] Tests pass locally
- [ ] Documentation updated
- [ ] Commits are clear and descriptive
- [ ] Branch is up-to-date with main

### PR Title Format

Use conventional commits format:

```
feat: add ACME DNS-01 challenge support
fix: correct certificate expiration check
docs: update installation guide
test: add integration tests for SCEP
refactor: simplify CA engine code
chore: update dependencies
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Test additions/changes
- `refactor`: Code refactoring
- `chore`: Maintenance tasks
- `perf`: Performance improvements

### PR Description Template

```markdown
## Description
Brief description of changes

## Motivation
Why is this change needed?

## Changes
- List of changes made
- Another change

## Testing
How was this tested?

## Related Issues
Fixes #123
Related to #456

## Screenshots (if applicable)
[Add screenshots]

## Checklist
- [ ] Tests pass
- [ ] Documentation updated
- [ ] Follows coding standards
```

### Review Process

1. **Automated Checks**
   - CI/CD pipeline runs
   - Code quality checks
   - Test suite execution

2. **Manual Review**
   - Code review by maintainer(s)
   - Feedback provided
   - Revisions requested (if needed)

3. **Approval**
   - At least one approval required
   - All checks must pass
   - Conflicts resolved

4. **Merge**
   - Squash and merge (default)
   - Rebase and merge (for clean commits)

## Issue Reporting

### Bug Reports

**Include:**
- UCM version
- Operating system
- Python version
- Steps to reproduce
- Expected behavior
- Actual behavior
- Error messages/logs
- Screenshots (if applicable)

**Template:**
```markdown
**Version:** 1.8.2
**OS:** Ubuntu 22.04
**Python:** 3.10.12

**Description:**
Brief description of the bug

**Steps to Reproduce:**
1. Go to...
2. Click on...
3. See error

**Expected Behavior:**
What should happen

**Actual Behavior:**
What actually happens

**Logs:**
```
[paste relevant logs]
```

**Screenshots:**
[if applicable]
```

### Feature Requests

**Include:**
- Use case description
- Proposed solution
- Alternatives considered
- Additional context

## Documentation

### Types of Documentation

1. **Code Documentation**
   - Docstrings for functions/classes
   - Inline comments for complex logic
   - Type hints

2. **User Documentation**
   - Installation guides
   - Configuration guides
   - How-to guides
   - Troubleshooting

3. **Developer Documentation**
   - Architecture overview
   - API documentation
   - Contributing guide
   - Release process

### Documentation Standards

**Markdown Files:**
- Use `.md` extension
- Follow CommonMark syntax
- Include table of contents for long docs
- Use code blocks with language specifiers

**Example Documentation:**
````markdown
# Feature Name

## Overview
Brief description

## Installation
```bash
pip install package
```

## Usage
```python
from package import Feature
feature = Feature()
```

## Configuration
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable feature |

## See Also
- [Related Doc](link)
````

## Communication

### Getting Help

**Channels:**
- GitHub Issues: Bug reports and feature requests
- GitHub Discussions: General questions
- Email: security@example.com (security issues only)

### Asking Questions

**Good Question:**
```
I'm trying to configure mTLS authentication with nginx, but clients
are getting 403 errors. I've set ssl_client_certificate to ca.crt
and ssl_verify_client to on. The client certificate is valid and
issued by the same CA. Here are the relevant nginx logs: [logs]

What am I missing?
```

**Better than:**
```
mTLS not working help!!!
```

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Acknowledged in commit messages

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (MIT License).

## See Also

- [Architecture](Architecture.md) - System architecture
- [Building](Building.md) - Build instructions
- [Security](Security.md) - Security guidelines

---

**Questions?** Open an issue or discussion on GitHub!

**Thank you for contributing to Ultimate CA Manager! 🎉**
