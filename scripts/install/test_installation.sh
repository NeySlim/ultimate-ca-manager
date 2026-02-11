#!/bin/bash
#
# UCM Installation Simulation Test
# Tests complete installation flow without actually installing
#

set -e

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  UCM Installation Simulation Test                     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Test function
test_step() {
    local description="$1"
    local command="$2"
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    echo -e "${YELLOW}[$TESTS_TOTAL] Testing: $description${NC}"
    
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}    ✅ PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}    ❌ FAIL${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}1. Pre-Installation Checks${NC}"
echo ""

test_step "Python 3 available" "command -v python3"
test_step "Python version >= 3.10" "python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'"
test_step "pip3 available" "command -v pip3"
test_step "OpenSSL available" "command -v openssl"
test_step "systemd available" "command -v systemctl"

echo ""
echo -e "${BLUE}2. File Structure Checks${NC}"
echo ""

test_step "Backend directory exists" "[ -d backend ]"
test_step "Frontend directory exists" "[ -d frontend ]"
test_step "Requirements.txt exists" "[ -f backend/requirements.txt ]"
test_step "WSGI entry point exists" "[ -f wsgi.py ]"
test_step "Gunicorn config exists" "[ -f gunicorn.conf.py ]"

echo ""
echo -e "${BLUE}3. Package Files Checks${NC}"
echo ""

# DEB
test_step "DEB control file exists" "[ -f packaging/debian/control ]"
test_step "DEB postinst exists" "[ -f packaging/debian/postinst ]"
test_step "DEB service file exists" "[ -f packaging/debian/ucm.service ]"
test_step "DEB build script exists" "[ -f packaging/scripts/build-deb.sh ]"

# RPM
test_step "RPM spec file exists" "[ -f packaging/rpm/ucm.spec ]"
test_step "RPM service file exists" "[ -f packaging/rpm/ucm.service ]"
test_step "RPM build script exists" "[ -f packaging/scripts/build-rpm.sh ]"

# Common
test_step "Configure script exists" "[ -f packaging/scripts/ucm-configure ]"

echo ""
echo -e "${BLUE}4. Docker Files Checks${NC}"
echo ""

test_step "Dockerfile exists" "[ -f Dockerfile ]"
test_step "docker-compose.yml exists" "[ -f docker-compose.yml ]"
test_step "docker-entrypoint.sh exists" "[ -f docker/entrypoint.sh ]"
test_step ".env.example exists" "[ -f .env.example ]"
test_step "docker-helper.sh exists" "[ -f docker-helper.sh ]"

echo ""
echo -e "${BLUE}5. Dependencies Test${NC}"
echo ""

# Create venv for testing
echo "   Creating test virtualenv..."
TEST_VENV="/tmp/ucm-test-venv-$$"
python3 -m venv "$TEST_VENV" > /dev/null 2>&1

test_step "Virtualenv created" "[ -d $TEST_VENV ]"
test_step "Can install Flask" "$TEST_VENV/bin/pip install -q Flask==3.1.2"
test_step "Can install Flask-Caching" "$TEST_VENV/bin/pip install -q Flask-Caching==2.3.0"
test_step "Can install cryptography" "$TEST_VENV/bin/pip install -q cryptography==46.0.5"
test_step "Can install pyasn1" "$TEST_VENV/bin/pip install -q pyasn1==0.6.1"

# Cleanup venv
rm -rf "$TEST_VENV"

echo ""
echo -e "${BLUE}6. Application Import Test${NC}"
echo ""

# Test imports in isolated environment
TEST_DIR="/tmp/ucm-import-test-$$"
mkdir -p "$TEST_DIR"

test_step "Can import config.settings" "python3 -c 'import sys; sys.path.insert(0, \"backend\"); from config.settings import get_config'"
test_step "Can import models" "python3 -c 'import sys; sys.path.insert(0, \"backend\"); from models import db, User'"
test_step "Can import app factory" "python3 -c 'import sys; sys.path.insert(0, \"backend\"); from app import create_app'"

rm -rf "$TEST_DIR"

echo ""
echo -e "${BLUE}7. Database Initialization Test${NC}"
echo ""

# Full initialization test (requires venv with all dependencies)
if [ -d "venv" ]; then
    echo "   Using existing venv..."
    test_step "Database init works" "source venv/bin/activate && python3 -c '
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, \"backend\")
test_dir = tempfile.mkdtemp()
for d in [\"backend/data\", \"frontend/static\", \"frontend/templates\"]:
    Path(f\"{test_dir}/{d}\").mkdir(parents=True, exist_ok=True)
os.chdir(test_dir)
Path(\".env\").write_text(f\"SECRET_KEY=test\\nJWT_SECRET_KEY=test\\nSQLALCHEMY_DATABASE_URI=sqlite:///{test_dir}/backend/data/test.db\\nHTTPS_AUTO_GENERATE=false\")
from dotenv import load_dotenv
load_dotenv()
from app import create_app
app = create_app(\"testing\")
import shutil
shutil.rmtree(test_dir)
'"
else
    echo "   ${YELLOW}⚠️  Skipped (no venv found)${NC}"
fi

echo ""
echo -e "${BLUE}8. Configuration Files Test${NC}"
echo ""

test_step ".env.example has required vars" "grep -q 'SECRET_KEY' .env.example"
test_step ".env.example has JWT config" "grep -q 'JWT_SECRET_KEY' .env.example"
test_step ".env.example has DB config" "grep -q 'SQLALCHEMY_DATABASE_URI' .env.example"
test_step ".env.example has FQDN config" "grep -q 'FQDN' .env.example"

echo ""
echo -e "${BLUE}9. Script Syntax Validation${NC}"
echo ""

# Validate all bash scripts
SCRIPTS=(
    "docker/entrypoint.sh"
    "docker-helper.sh"
    "packaging/scripts/build-deb.sh"
    "packaging/scripts/build-rpm.sh"
    "packaging/scripts/ucm-configure"
    "packaging/debian/config"
    "packaging/debian/postinst"
    "packaging/debian/preinst"
    "packaging/debian/postrm"
)

for script in "${SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        test_step "$(basename $script) syntax valid" "bash -n $script"
    fi
done

echo ""
echo -e "${BLUE}10. Documentation Test${NC}"
echo ""

test_step "PACKAGE_INSTALL_GUIDE.md exists" "[ -f PACKAGE_INSTALL_GUIDE.md ]"
test_step "RPM_INSTALL_GUIDE.md exists" "[ -f RPM_INSTALL_GUIDE.md ]"
test_step "DOCKER_QUICKSTART.md exists" "[ -f DOCKER_QUICKSTART.md ]"
test_step "UPGRADE.md exists" "[ -f UPGRADE.md ]"

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Test Results Summary                                  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Total Tests: ${BLUE}${TESTS_TOTAL}${NC}"
echo -e "  Passed:      ${GREEN}${TESTS_PASSED}${NC}"
echo -e "  Failed:      ${RED}${TESTS_FAILED}${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✅✅✅ ALL TESTS PASSED! ✅✅✅${NC}"
    echo ""
    echo -e "${GREEN}UCM is ready for:${NC}"
    echo "  - DEB package build"
    echo "  - RPM package build"
    echo "  - Docker deployment"
    echo "  - Production installation"
    echo ""
    exit 0
else
    PASS_RATE=$((TESTS_PASSED * 100 / TESTS_TOTAL))
    echo -e "${YELLOW}⚠️  Some tests failed (${PASS_RATE}% pass rate)${NC}"
    echo ""
    echo "Review failures above before proceeding with installation."
    echo ""
    exit 1
fi
