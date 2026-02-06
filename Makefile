# Purple Computer Makefile
# Convenient shortcuts for development and testing

.PHONY: help setup run run-sleep-demo run-demo run-demo-segment test lint build-packs build-iso clean clean-iso clean-all recording-setup record-demo voice-clips voice-variants

help:
	@echo "Purple Computer - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup           - Install dependencies and build packs"
	@echo "  make recording-setup - Install screen recording tools (VM only)"
	@echo ""
	@echo "Running:"
	@echo "  make run             - Run Purple Computer locally"
	@echo "  make run-demo        - Run with demo auto-start"
	@echo "  make run-demo-segment SEGMENT=tune - Play one demo segment"
	@echo "  make run-sleep-demo  - Test sleep/power states (accelerated timing)"
	@echo "  make test            - Run tests"
	@echo ""
	@echo "Recording:"
	@echo "  make record-demo      - Record demo to recordings/demo.mp4 (VM only)"
	@echo "  make record-demo-test - Record 5s test clip (for testing recording pipeline)"
	@echo "  make voice-clips     - Generate TTS voice clips for demo"
	@echo "  make voice-variants  - Generate 5 variants of each clip (for auditioning)"
	@echo ""
	@echo "Building:"
	@echo "  make build-packs     - Build content packs"
	@echo "  make build-iso       - Build bootable ISO for installation"
	@echo ""
	@echo "Cleaning:"
	@echo "  make clean           - Remove test environment"
	@echo "  make clean-iso       - Remove ISO build artifacts"
	@echo "  make clean-all       - Remove everything"
	@echo ""
	@echo "Controls:"
	@echo "  F1-F3      - Switch modes (Ask, Play, Write)"
	@echo "  Ctrl+V     - Cycle views (Screen, Line, Ears)"
	@echo "  F12        - Toggle dark/light theme"
	@echo ""
	@echo "For more info, see README.md"

setup:
	@echo "Setting up Purple Computer development environment..."
	./scripts/setup_dev.sh

run:
	@echo "Running Purple Computer locally..."
	PURPLE_TEST_BATTERY=1 ./scripts/run_local.sh

run-demo:
	@echo "Running Purple Computer with demo auto-start..."
	PURPLE_TEST_BATTERY=1 PURPLE_DEMO_AUTOSTART=1 ./scripts/run_local.sh

run-demo-segment:
	PURPLE_TEST_BATTERY=1 PURPLE_DEMO_AUTOSTART=1 PURPLE_DEMO_SEGMENT=$(SEGMENT) ./scripts/run_local.sh

run-sleep-demo:
	@echo "Running sleep/power demo mode..."
	@echo ""
	@echo "Accelerated timing for testing:"
	@echo "  0s   - Start (normal UI)"
	@echo "  2s   - Sleep screen appears"
	@echo "  6s   - Screen dims"
	@echo "  10s  - Screen off"
	@echo "  15s  - Shutdown warning"
	@echo "  20s  - Shutdown (simulated)"
	@echo ""
	@echo "Press any key at any point to reset the idle timer."
	@echo "Press Ctrl+C to exit."
	@echo ""
	PURPLE_TEST_BATTERY=1 PURPLE_SLEEP_DEMO=1 ./scripts/run_local.sh

test:
	@.venv/bin/python -m pytest tests/ -v

lint:
	@.venv/bin/ruff check purple_tui/ tools/ scripts/ tests/

lint-fix:
	@.venv/bin/ruff check purple_tui/ tools/ scripts/ tests/ --fix

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

recording-setup:
	@echo "Setting up screen recording tools..."
	./recording-setup/setup.sh

record-demo:
	@echo "Generating voice clips (if needed)..."
	@.venv/bin/python scripts/generate_voice_clips.py
	@echo "Recording demo..."
	./recording-setup/record-demo.sh

voice-clips:
	@echo "Generating TTS voice clips for demo..."
	@.venv/bin/python scripts/generate_voice_clips.py

voice-variants:
	@echo "Generating 5 variants of each voice clip..."
	@.venv/bin/python scripts/generate_voice_clips.py --variants 5
	@echo ""
	@echo "Listen to variants and copy the best one over the original."

.DEFAULT_GOAL := help
