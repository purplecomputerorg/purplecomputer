#!/bin/bash
# Verify Purple Computer Installation
# Quick sanity check that everything is set up correctly

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

check() {
    echo -n "Checking $1... "
    if eval "$2" &>/dev/null; then
        echo -e "${GREEN}✓${NC}"
        ((PASS++))
        return 0
    else
        echo -e "${RED}✗${NC}"
        ((FAIL++))
        return 1
    fi
}

check_file() {
    echo -n "Checking $1... "
    if [ -f "$2" ]; then
        echo -e "${GREEN}✓${NC}"
        ((PASS++))
    else
        echo -e "${RED}✗${NC} (missing)"
        ((FAIL++))
    fi
}

echo "Purple Computer Installation Verification"
echo "=========================================="
echo ""

# Python checks
check "Python 3" "command -v python3"
check "pip3" "command -v pip3"
check "IPython module" "python3 -c 'import IPython'"
check "colorama module" "python3 -c 'import colorama'"
check "termcolor module" "python3 -c 'import termcolor'"
check "packaging module" "python3 -c 'import packaging'"

echo ""
echo "Core Files:"
check_file "repl.py" "$PROJECT_ROOT/purple_repl/repl.py"
check_file "pack_manager.py" "$PROJECT_ROOT/purple_repl/pack_manager.py"
check_file "parent_auth.py" "$PROJECT_ROOT/purple_repl/parent_auth.py"
check_file "update_manager.py" "$PROJECT_ROOT/purple_repl/update_manager.py"

echo ""
echo "Scripts:"
check_file "run_local.sh" "$PROJECT_ROOT/scripts/run_local.sh"
check_file "run_docker.sh" "$PROJECT_ROOT/scripts/run_docker.sh"
check_file "setup_dev.sh" "$PROJECT_ROOT/scripts/setup_dev.sh"
check_file "build_pack.py" "$PROJECT_ROOT/scripts/build_pack.py"

echo ""
echo "Example Packs:"
check_file "core-emoji pack source" "$PROJECT_ROOT/packs/core-emoji/manifest.json"
check_file "education-basics pack source" "$PROJECT_ROOT/packs/education-basics/manifest.json"

# Try to build packs if they don't exist
if [ ! -f "$PROJECT_ROOT/packs/core-emoji.purplepack" ]; then
    echo ""
    echo "Building example packs..."
    cd "$PROJECT_ROOT"
    python3 scripts/build_pack.py packs/core-emoji packs/core-emoji.purplepack
    python3 scripts/build_pack.py packs/education-basics packs/education-basics.purplepack
fi

check_file "core-emoji.purplepack" "$PROJECT_ROOT/packs/core-emoji.purplepack"
check_file "education-basics.purplepack" "$PROJECT_ROOT/packs/education-basics.purplepack"

# Docker check (optional)
echo ""
echo "Optional:"
if command -v docker &>/dev/null; then
    if docker info &>/dev/null 2>&1; then
        echo -e "Docker... ${GREEN}✓${NC} (running)"
    else
        echo -e "Docker... ${YELLOW}⚠${NC} (installed but not running)"
    fi
else
    echo -e "Docker... ${YELLOW}⚠${NC} (not installed, optional for testing)"
fi

# Summary
echo ""
echo "=========================================="
if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}All checks passed! ($PASS/$((PASS+FAIL)))${NC}"
    echo ""
    echo "You're ready to run Purple Computer:"
    echo "  ./scripts/run_local.sh"
    echo ""
    exit 0
else
    echo -e "${RED}Some checks failed ($FAIL failed, $PASS passed)${NC}"
    echo ""
    echo "Run setup to fix:"
    echo "  ./scripts/setup_dev.sh"
    echo ""
    exit 1
fi
