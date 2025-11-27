#!/bin/bash
# Purple Computer Development Setup
# Quick setup for local development and testing

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Purple Computer Development Setup         ║"
echo "╔══════════════════════════════════════════════╗"
echo ""

cd "$PROJECT_ROOT"

# Detect OS
OS="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="mac"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
fi

echo_info "Detected OS: $OS"

# Check Python
echo_step "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found."
    if [ "$OS" = "mac" ]; then
        echo "Install with: brew install python3"
    else
        echo "Install with: sudo apt install python3 python3-pip"
    fi
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo_info "✓ Python $PYTHON_VERSION found"

# Create virtual environment
echo_step "Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo_info "✓ Created .venv"
else
    echo_info "✓ .venv already exists"
fi

# Activate venv
source .venv/bin/activate

# Install Python dependencies
echo_step "Installing Python dependencies into venv..."
pip install --upgrade pip
pip install ipython colorama termcolor packaging traitlets simple-term-menu rich

echo_info "✓ Python dependencies installed in virtual environment"

# Build example packs
echo_step "Building example packs..."
if [ ! -f "packs/core-emoji.purplepack" ]; then
    python3 scripts/build_pack.py packs/core-emoji packs/core-emoji.purplepack
    echo_info "✓ Built core-emoji.purplepack"
else
    echo_info "✓ core-emoji.purplepack exists"
fi

if [ ! -f "packs/education-basics.purplepack" ]; then
    python3 scripts/build_pack.py packs/education-basics packs/education-basics.purplepack
    echo_info "✓ Built education-basics.purplepack"
else
    echo_info "✓ education-basics.purplepack exists"
fi

# Check Docker (optional)
echo_step "Checking Docker installation (optional)..."
if command -v docker &> /dev/null; then
    if docker info &> /dev/null 2>&1; then
        echo_info "✓ Docker is installed and running"
        DOCKER_AVAILABLE=true
    else
        echo_warn "Docker is installed but not running"
        DOCKER_AVAILABLE=false
    fi
else
    echo_warn "Docker not found (optional for testing)"
    DOCKER_AVAILABLE=false
fi

# Summary
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Setup Complete!                            ║"
echo "╔══════════════════════════════════════════════╗"
echo ""
echo_info "Virtual environment created at .venv/"
echo_info "Activate it with: source .venv/bin/activate"
echo ""
echo_info "You can now run Purple Computer:"
echo ""
echo "  1. Local mode (Mac/Linux):"
echo "     make run"
echo "     (or ./scripts/run_local.sh)"
echo ""

if [ "$DOCKER_AVAILABLE" = true ]; then
    echo "  2. Docker mode (full simulation):"
    echo "     make run-docker"
    echo "     (or ./scripts/run_docker.sh)"
    echo ""
fi

echo_info "The scripts will automatically activate the venv"
