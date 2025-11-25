#!/bin/bash
# Docker-based Purple Computer Runner
# Full simulation of Purple Computer environment

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
echo "║   Purple Computer - Docker Test Mode        ║"
echo "╔══════════════════════════════════════════════╗"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker not found. Please install Docker Desktop."
    echo "Download from: https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo "Error: Docker is not running. Please start Docker Desktop."
    exit 1
fi

cd "$PROJECT_ROOT"

# Build packs if they don't exist
if [ ! -f "packs/core-emoji.purplepack" ]; then
    echo_step "Building example packs..."
    python3 scripts/build_pack.py packs/core-emoji packs/core-emoji.purplepack
    python3 scripts/build_pack.py packs/education-basics packs/education-basics.purplepack
fi

# Parse command line arguments
MODE="interactive"
BUILD=false

for arg in "$@"; do
    case $arg in
        --build)
            BUILD=true
            shift
            ;;
        --shell)
            MODE="shell"
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --build    Force rebuild of Docker image"
            echo "  --shell    Start a bash shell instead of REPL"
            echo "  --help     Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                # Run Purple Computer REPL"
            echo "  $0 --build        # Rebuild image and run"
            echo "  $0 --shell        # Start bash shell for debugging"
            exit 0
            ;;
    esac
done

# Build or pull image
if [ "$BUILD" = true ]; then
    echo_step "Building Docker image..."
    docker build -t purplecomputer:latest .
else
    if ! docker image inspect purplecomputer:latest &> /dev/null; then
        echo_step "Building Docker image (first time)..."
        docker build -t purplecomputer:latest .
    else
        echo_info "Using existing Docker image (use --build to rebuild)"
    fi
fi

# Run container
echo_step "Starting Purple Computer container..."
echo_info "Press Ctrl+C to access parent mode"
echo_info "Type 'exit()' or press Ctrl+D to quit"
echo ""

if [ "$MODE" = "shell" ]; then
    echo_info "Starting bash shell..."
    docker run -it --rm \
        -v "$PROJECT_ROOT/purple_repl:/home/purple/.purple:ro" \
        -v "$PROJECT_ROOT/packs:/home/purple/packs:ro" \
        -e HOME=/home/purple \
        -e IPYTHONDIR=/home/purple/.ipython \
        -e TERM=xterm-256color \
        purplecomputer:latest \
        /bin/bash
else
    docker run -it --rm \
        -v "$PROJECT_ROOT/purple_repl:/home/purple/.purple:ro" \
        -v "$PROJECT_ROOT/packs:/home/purple/packs:ro" \
        -e HOME=/home/purple \
        -e IPYTHONDIR=/home/purple/.ipython \
        -e TERM=xterm-256color \
        purplecomputer:latest
fi

echo ""
echo_info "Purple Computer session ended."
