#!/bin/bash
# Purple Computer Build & Syntax Checker
# Checks all Python files for syntax errors and basic import issues

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo_info() {
    echo -e "${GREEN}[✓]${NC} $1"
}

echo_error() {
    echo -e "${RED}[✗]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

echo_step() {
    echo -e "${BLUE}[→]${NC} $1"
}

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Purple Computer Build Check                ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

cd "$PROJECT_ROOT"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo_error "python3 not found. Please install Python 3."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo_info "Using Python $PYTHON_VERSION"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo_step "Activating virtual environment..."
    source .venv/bin/activate
    echo_info "Virtual environment activated"
else
    echo_warn "No .venv found. Run 'make setup' first for best results."
fi

echo ""
echo_step "Checking Python syntax in all files..."
echo ""

ERRORS=0
FILES_CHECKED=0

# Find all Python files
while IFS= read -r -d '' file; do
    FILES_CHECKED=$((FILES_CHECKED + 1))

    # Check syntax using py_compile
    if python3 -m py_compile "$file" 2>/dev/null; then
        echo_info "$(basename "$file")"
    else
        echo_error "Syntax error in: $file"
        python3 -m py_compile "$file" 2>&1 | sed 's/^/  /'
        ERRORS=$((ERRORS + 1))
    fi
done < <(find purple_repl packs scripts -name "*.py" -type f -print0 2>/dev/null)

echo ""
echo_step "Checking module imports..."
echo ""

# Test critical imports
TEST_IMPORTS=(
    "purple_repl.repl"
    "purple_repl.pack_manager"
    "purple_repl.parent_auth"
    "purple_repl.emoji_lib"
    "purple_repl.tts"
)

for module in "${TEST_IMPORTS[@]}"; do
    if python3 -c "import sys; sys.path.insert(0, 'purple_repl'); import ${module##*.}" 2>/dev/null; then
        echo_info "$module"
    else
        echo_warn "Could not import $module (may need dependencies)"
        # Don't count as error - might be missing optional deps
    fi
done

echo ""
echo_step "Checking mode modules..."
echo ""

# Check each mode can be imported
for mode_file in purple_repl/modes/*.py; do
    if [ "$(basename "$mode_file")" != "__init__.py" ]; then
        mode_name=$(basename "$mode_file" .py)
        if python3 -c "import sys; sys.path.insert(0, 'purple_repl'); from modes import $mode_name" 2>/dev/null; then
            echo_info "modes.$mode_name"
        else
            echo_error "Failed to import modes.$mode_name"
            ERRORS=$((ERRORS + 1))
        fi
    fi
done

echo ""
echo_step "Checking pack data files..."
echo ""

# Check music mode pack
if [ -f "packs/music_mode_basic/data/music_mode.py" ]; then
    if python3 -m py_compile "packs/music_mode_basic/data/music_mode.py" 2>/dev/null; then
        echo_info "music_mode.py"
    else
        echo_error "Syntax error in music_mode.py"
        ERRORS=$((ERRORS + 1))
    fi
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Summary                                    ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo_info "Files checked: $FILES_CHECKED"

if [ $ERRORS -eq 0 ]; then
    echo_info "No syntax errors found!"
    echo ""
    echo -e "${GREEN}✓ Build check passed${NC}"
    echo ""
    exit 0
else
    echo_error "Found $ERRORS error(s)"
    echo ""
    echo -e "${RED}✗ Build check failed${NC}"
    echo ""
    exit 1
fi
