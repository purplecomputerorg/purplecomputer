#!/bin/bash
# Purple Computer Dependency Installer
# Install all required dependencies for development

set -e

echo "Purple Computer Dependency Installer"
echo "====================================="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

REQUIRED_VERSION="3.8"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "Error: Python 3.8 or higher required"
    exit 1
fi

echo ""
echo "Installing Python packages..."
echo ""

# Core dependencies
pip3 install --user ipython colorama termcolor

# Optional dependencies
echo ""
echo "Installing optional dependencies..."
pip3 install --user pyttsx3 || echo "Warning: pyttsx3 install failed (optional)"

# Development dependencies
echo ""
echo "Installing development dependencies..."
pip3 install --user flake8 black isort pytest || echo "Warning: dev tools install failed (optional)"

echo ""
echo "====================================="
echo "Installation complete!"
echo ""
echo "Core dependencies:"
echo "  ✓ IPython"
echo "  ✓ colorama"
echo "  ✓ termcolor"
echo ""
echo "To test Purple Computer:"
echo "  ./scripts/dev-run.sh"
