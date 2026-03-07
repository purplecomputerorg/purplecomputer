# Purple Computer
# Run `just` to see all available commands

# Show available commands
default:
    @just --list

# Install dependencies and build packs
setup:
    @echo "Setting up Purple Computer development environment..."
    ./scripts/setup_dev.sh

# Run Purple Computer locally
run:
    PURPLE_TEST_BATTERY=1 ./scripts/run_local.sh

# Run with demo auto-start
run-demo:
    PURPLE_TEST_BATTERY=1 PURPLE_DEMO_AUTOSTART=1 ./scripts/run_local.sh

# Play one demo segment
run-demo-segment segment:
    PURPLE_TEST_BATTERY=1 PURPLE_DEMO_AUTOSTART=1 PURPLE_DEMO_SEGMENT={{segment}} ./scripts/run_local.sh

# Test sleep/power states (accelerated timing)
run-sleep-demo:
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

# Run tests
test:
    .venv/bin/python -m pytest tests/ -v

# Run linter
lint:
    .venv/bin/ruff check purple_tui/ tools/ scripts/ tests/

# Run linter with auto-fix
lint-fix:
    .venv/bin/ruff check purple_tui/ tools/ scripts/ tests/ --fix

# Build content packs
build-packs:
    @echo "Building content packs..."
    cd packs/core-emoji && tar -czvf ../core-emoji.purplepack manifest.json content/
    cd packs/core-definitions && tar -czvf ../core-definitions.purplepack manifest.json content/
    @echo "✓ Packs built"

# Build bootable ISO for installation
build-iso:
    @echo "Building Purple Computer ISO..."
    @echo "This will download Ubuntu Server ISO (~1.4GB) and create a bootable image"
    @echo ""
    ./autoinstall/build-iso.sh
    @echo ""
    @echo "✓ ISO built: purple-computer.iso"

# Remove test environment
clean:
    @echo "Cleaning local test environment..."
    rm -rf .test_home/
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    @echo "✓ Test environment removed"

# Remove ISO build artifacts
clean-iso:
    @echo "Cleaning ISO build artifacts..."
    rm -rf autoinstall/build/
    rm -f purple-computer.iso
    @echo "✓ ISO build artifacts removed"

# Remove everything
clean-all: clean clean-iso
    @echo "✓ All cleaned"

# Install screen recording tools (VM only)
recording-setup:
    ./recording-setup/setup.sh

# Record demo with background music (VM only)
record-demo:
    @echo "Generating voice clips (if needed)..."
    .venv/bin/python scripts/generate_voice_clips.py
    @echo "Recording demo (with background music)..."
    ./recording-setup/record-demo.sh

# Record demo without background music
record-demo-no-music:
    @echo "Generating voice clips (if needed)..."
    .venv/bin/python scripts/generate_voice_clips.py
    @echo "Recording demo (no background music)..."
    PURPLE_NO_MUSIC=1 ./recording-setup/record-demo.sh

# Record 5s test clip (for testing recording pipeline)
record-demo-test:
    ./recording-setup/record-demo.sh recordings/demo-test.mp4 5

# Generate TTS voice clips for demo
voice-clips *args:
    @echo "Generating TTS voice clips for demo..."
    .venv/bin/python scripts/generate_voice_clips.py {{args}}

# Generate 5 variants of each clip (for auditioning)
voice-variants:
    @echo "Generating 5 variants of each voice clip..."
    .venv/bin/python scripts/generate_voice_clips.py --variants 5
    @echo ""
    @echo "Listen to variants and copy the best one over the original."

# Generate letter/number name clips for Play Mode
letter-clips *args:
    @echo "Generating letter/number name clips for Play Mode..."
    .venv/bin/python scripts/generate_letter_clips.py {{args}}

# Verify deterministic TTS output
debug-tts:
    .venv/bin/python scripts/debug_tts.py

# Clear cached TTS audio files
clear-tts-cache:
    .venv/bin/python -c "from purple_tui.tts import clear_cache; n = clear_cache(); print(f'Cleared {n} cached TTS files')"

# Apply zoom keyframes to demo video
apply-zoom:
    .venv/bin/python recording-setup/apply_zoom.py recordings/demo_cropped.mp4 recording-setup/zoom_events.json recordings/demo_zoomed.mp4

# Open zoom keyframe editor in browser
zoom-editor:
    python recording-setup/zoom_editor_server.py

# Generate Ed25519 key pair for USB update signing
keygen:
    .venv/bin/python tools/usb_update_keygen.py

# Create signed USB update package
create-update version output *args:
    .venv/bin/python tools/create_usb_update.py --version {{version}} --output {{output}} {{args}}

# Run Python with venv (e.g., just python script.py, just python -c 'print(1)')
python *args:
    @.venv/bin/python {{args}}

# Run Python from stdin (e.g., echo 'print("hi")' | just pystdin)
pystdin:
    @.venv/bin/python -
