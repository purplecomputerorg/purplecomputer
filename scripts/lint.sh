#!/bin/bash
# Purple Computer Linter
# Check Python code style and quality

set -e

echo "Purple Computer Code Linter"
echo "============================"
echo ""

# Check if in right directory
if [ ! -d "purple_repl" ]; then
    echo "Error: Run from repository root"
    exit 1
fi

# Check for tools
check_tool() {
    if ! command -v $1 &> /dev/null; then
        echo "✗ $1 not installed"
        return 1
    else
        echo "✓ $1"
        return 0
    fi
}

echo "Checking for linting tools..."
MISSING=0

check_tool "flake8" || MISSING=1
check_tool "black" || MISSING=1
check_tool "isort" || MISSING=1

if [ $MISSING -eq 1 ]; then
    echo ""
    echo "Install missing tools:"
    echo "  pip3 install flake8 black isort"
    exit 1
fi

echo ""
echo "Running linters..."
echo ""

# Run black (formatter check)
echo "--- Black (formatter) ---"
black --check purple_repl/ || true
echo ""

# Run isort (import sorting)
echo "--- isort (imports) ---"
isort --check purple_repl/ || true
echo ""

# Run flake8 (style checker)
echo "--- flake8 (style) ---"
flake8 purple_repl/ --max-line-length=100 --ignore=E203,W503 || true
echo ""

echo "============================"
echo "Linting complete!"
echo ""
echo "To auto-fix formatting:"
echo "  black purple_repl/"
echo "  isort purple_repl/"
