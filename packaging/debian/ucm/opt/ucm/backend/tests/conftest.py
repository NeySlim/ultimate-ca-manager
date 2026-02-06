"""
pytest configuration and fixtures for UCM backend tests
"""
import pytest
import os
import sys
import tempfile

# Add backend to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def temp_db():
    """Create a temporary database file for testing"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        yield f.name
    # Cleanup
    if os.path.exists(f.name):
        os.unlink(f.name)

@pytest.fixture
def test_config(temp_db):
    """Test configuration with temporary database"""
    return {
        'DATABASE_PATH': temp_db,
        'SECRET_KEY': 'test-secret-key-for-testing-only',
        'ENV': 'test'
    }
