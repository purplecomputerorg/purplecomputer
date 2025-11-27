# Purple Computer Makefile
# Convenient shortcuts for development and testing

.PHONY: help setup run run-docker build-packs build-iso clean test check docker-build docker-shell clean-iso

help:
	@echo "Purple Computer - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup          - Install dependencies and build packs"
	@echo ""
	@echo "Running:"
	@echo "  make run            - Run Purple Computer locally (fast)"
	@echo "  make run-docker     - Run Purple Computer in Docker (full simulation)"
	@echo "  make docker-shell   - Open bash shell in Docker"
	@echo ""
	@echo "Building & Testing:"
	@echo "  make check          - Check Python syntax and imports"
	@echo "  make test           - Run all tests (syntax + unit tests)"
	@echo "  make build-packs    - Build example packs"
	@echo "  make build-iso      - Build bootable ISO for VM/hardware install"
	@echo "  make docker-build   - Rebuild Docker image"
	@echo ""
	@echo "Cleaning:"
	@echo "  make clean          - Remove test environment"
	@echo "  make clean-docker   - Remove Docker containers and volumes"
	@echo "  make clean-iso      - Remove ISO build artifacts"
	@echo "  make clean-all      - Remove everything (test env + Docker + ISO)"
	@echo ""
	@echo "For more info, see README.md and MANUAL.md"

setup:
	@echo "Setting up Purple Computer development environment..."
	./scripts/setup_dev.sh

run:
	@echo "Running Purple Computer locally..."
	./scripts/run_local.sh

run-docker:
	@echo "Running Purple Computer in Docker..."
	./scripts/run_docker.sh

docker-build:
	@echo "Building Docker image..."
	./scripts/run_docker.sh --build

docker-shell:
	@echo "Opening Docker shell..."
	./scripts/run_docker.sh --shell

build-packs:
	@echo "Building example packs..."
	@bash -c "if [ -d .venv ]; then source .venv/bin/activate; fi; python scripts/build_pack.py packs/core-emoji packs/core-emoji.purplepack"
	@bash -c "if [ -d .venv ]; then source .venv/bin/activate; fi; python scripts/build_pack.py packs/education-basics packs/education-basics.purplepack"
	@bash -c "if [ -d .venv ]; then source .venv/bin/activate; fi; python scripts/build_pack.py packs/music_mode_basic packs/music_mode_basic.purplepack"
	@echo "✓ Packs built"

build-iso:
	@echo "Building Purple Computer ISO..."
	@echo "This will download Ubuntu Server ISO (~1.4GB) and create a bootable image"
	@echo "Requirements: xorriso, isolinux, curl, wget"
	@echo ""
	./autoinstall/build-iso.sh
	@echo ""
	@echo "✓ ISO built successfully: purple-computer.iso"
	@echo "  Boot in VM with virtio-fs shared folder for live development"
	@echo "  See autoinstall/README.md for VM setup instructions"

clean:
	@echo "Cleaning local test environment..."
	rm -rf .test_home/
	@echo "✓ Test environment removed"

clean-docker:
	@echo "Cleaning Docker environment..."
	-docker rm -f purple-computer-test 2>/dev/null || true
	-docker volume rm purplecomputer_purple-data 2>/dev/null || true
	-docker volume rm purplecomputer_purple-config 2>/dev/null || true
	@echo "✓ Docker cleaned (image preserved, use 'docker rmi purplecomputer:latest' to remove image)"

clean-iso:
	@echo "Cleaning ISO build artifacts..."
	rm -rf autoinstall/build/
	rm -f purple-computer.iso
	@echo "✓ ISO build artifacts removed"

clean-all: clean clean-docker clean-iso
	@echo "✓ All test environments cleaned"

check:
	@echo "Checking Python syntax and imports..."
	./scripts/check.sh

test: check
	@echo "Running unit tests..."
	@echo "(Unit tests coming soon!)"
	# python3 -m pytest tests/

.DEFAULT_GOAL := help
