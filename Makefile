# Purple Computer Makefile
# Convenient shortcuts for development and testing

.PHONY: help setup run test build-packs build-iso clean clean-iso clean-all

help:
	@echo "Purple Computer - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup          - Install dependencies and build packs"
	@echo ""
	@echo "Running:"
	@echo "  make run            - Run Purple Computer locally"
	@echo "  make test           - Run tests"
	@echo ""
	@echo "Building:"
	@echo "  make build-packs    - Build content packs"
	@echo "  make build-iso      - Build bootable ISO for installation"
	@echo ""
	@echo "Cleaning:"
	@echo "  make clean          - Remove test environment"
	@echo "  make clean-iso      - Remove ISO build artifacts"
	@echo "  make clean-all      - Remove everything"
	@echo ""
	@echo "Controls:"
	@echo "  F1-F4      - Switch modes (Ask, Play, Listen, Write)"
	@echo "  Ctrl+V     - Cycle views (Screen, Line, Ears)"
	@echo "  F12        - Toggle dark/light theme"
	@echo ""
	@echo "For more info, see README.md"

setup:
	@echo "Setting up Purple Computer development environment..."
	./scripts/setup_dev.sh

run:
	@echo "Running Purple Computer locally..."
	./scripts/run_local.sh

test:
	@.venv/bin/python -m pytest tests/ -v

build-packs:
	@echo "Building content packs..."
	@cd packs/core-emoji && tar -czvf ../core-emoji.purplepack manifest.json content/
	@cd packs/core-definitions && tar -czvf ../core-definitions.purplepack manifest.json content/
	@echo "✓ Packs built"

build-iso:
	@echo "Building Purple Computer ISO..."
	@echo "This will download Ubuntu Server ISO (~1.4GB) and create a bootable image"
	@echo ""
	./autoinstall/build-iso.sh
	@echo ""
	@echo "✓ ISO built: purple-computer.iso"

clean:
	@echo "Cleaning local test environment..."
	rm -rf .test_home/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Test environment removed"

clean-iso:
	@echo "Cleaning ISO build artifacts..."
	rm -rf autoinstall/build/
	rm -f purple-computer.iso
	@echo "✓ ISO build artifacts removed"

clean-all: clean clean-iso
	@echo "✓ All cleaned"

.DEFAULT_GOAL := help
