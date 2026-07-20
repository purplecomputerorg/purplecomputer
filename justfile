# Purple Computer
# Run `just` to see all available commands

# Resolve the venv to the main repo's .venv, so recipes work from lanes worktrees too
venv := `dirname "$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || git rev-parse --git-common-dir)"` / ".venv"

# Show available commands
default:
    @just --list

# Show environment variables for testing
env:
    @echo "PURPLE_NO_AUDIO=1       Force audio off (test no-sound UX)"
    @echo "PURPLE_NO_EVDEV=1       Skip evdev input (use terminal keyboard)"
    @echo "PURPLE_DEV_MODE=1       Dev shortcuts, screenshots, debug keys"
    @echo "PURPLE_SLEEP_DEMO=1     Accelerated sleep/power timings"
    @echo "PURPLE_FAKE_USB=STATE   Simulate USB: caching|cached|removed"
    @echo "PURPLE_TEST_BATTERY=1   Show battery icon"
    @echo "PURPLE_DEMO_AUTOSTART=1 Auto-run demo sequence"
    @echo "PURPLE_DEMO_SEGMENT=X   Run specific demo segment"
    @echo "PURPLE_TTS_CACHE=path   Override TTS cache dir"
    @echo "PURPLE_SCREENSHOT_DIR=X Override screenshot output dir"
    @echo "PURPLE_POWER_LOG=1      Force power manager logging"
    @echo ""
    @echo "Example: PURPLE_NO_AUDIO=1 just run"

# Install dependencies and build packs
setup:
    @echo "Setting up Purple Computer development environment..."
    ./scripts/setup_dev.sh

# Run Purple Computer locally
run:
    PURPLE_TEST_BATTERY=1 ./scripts/run_local.sh

# Run in dev mode (no idle shutdown, debug logging)
run-dev:
    PURPLE_TEST_BATTERY=1 PURPLE_DEV_MODE=1 ./scripts/run_local.sh

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

# Headless UI preview: just preview [room] [actions...]
# Examples: just preview art, just preview play type:hello, just preview music code_panel
# Simulate USB states: PURPLE_FAKE_USB=caching|cached|removed just preview play
# Also works with run/run-dev: PURPLE_FAKE_USB=cached just run-dev
preview *args:
    @PYTHONPATH={{justfile_directory()}} {{venv}}/bin/python scripts/preview.py {{args}}

# Run tests (lint runs first; static checks catch undefined-name bugs before pytest spins up)
test: lint
    {{venv}}/bin/python -m pytest tests/ -v

# Test the install/reboot flow in isolation (no hardware needed)
test-install:
    {{venv}}/bin/python -m pytest tests/test_install_reboot.py -v

# Test the purple-reboot C binary (fallback chain, messages)
test-reboot:
    gcc -DTESTING -include tools/test_purple_reboot.c -o "${TMPDIR:-/tmp}/test_purple_reboot" tools/purple-reboot.c && "${TMPDIR:-/tmp}/test_purple_reboot"

# Test install.sh partition layout + BIOS grub-install against a loop-backed fake disk (needs sudo)
test-partitioning:
    sudo build-scripts/test-install-partitioning.sh

# Run linter
lint:
    {{venv}}/bin/ruff check purple_tui/ tools/ scripts/ tests/

# Run linter with auto-fix
lint-fix:
    {{venv}}/bin/ruff check purple_tui/ tools/ scripts/ tests/ --fix

# Build content packs
build-packs:
    @echo "Building content packs..."
    cd packs/core-emoji && tar -czvf ../core-emoji.purplepack manifest.json content/
    cd packs/core-definitions && tar -czvf ../core-definitions.purplepack manifest.json content/
    @echo "✓ Packs built"

# Regenerate the precomputed plural/singular lookup tables (after vocabulary changes)
build-plurals:
    @{{venv}}/bin/python3 scripts/build_plural_tables.py

# Remove test environment
clean:
    @echo "Cleaning local test environment..."
    rm -rf .test_home/
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    @echo "✓ Test environment removed"

# Release loop devices, mounts, and kpartx mappings from an interrupted build (keeps output ISOs and Docker image)
clean-build-resources:
    @echo "Releasing build resources..."
    @# Unmount everything under /opt/purple-installer in reverse order
    @for i in 1 2 3; do \
        mount | grep /opt/purple-installer | awk '{print $$3}' | sort -r | while read -r m; do \
            echo "  Unmounting $$m"; \
            sudo umount -f "$$m" 2>/dev/null || true; \
        done; \
    done
    @# Remove kpartx device-mapper entries
    @for mapping in $(ls /dev/mapper/loop* 2>/dev/null); do \
        echo "  Removing mapping $$mapping"; \
        sudo dmsetup remove "$$mapping" 2>/dev/null || true; \
    done
    @# Detach loop devices tied to the build
    @for loop in $(sudo losetup -a 2>/dev/null | grep -E 'purple-installer|purple-os\.img|\(deleted\)' | cut -d: -f1); do \
        echo "  Detaching $$loop"; \
        sudo losetup -d "$$loop" 2>/dev/null || true; \
    done
    @# Remove build working directory only (not output/)
    @if [ -d /opt/purple-installer/build ]; then \
        sudo rm -rf /opt/purple-installer/build; \
        sudo mkdir -p /opt/purple-installer/build; \
        echo "  Build dir reset"; \
    fi
    @echo "✓ Build resources released"


# Install screen recording tools (VM only)
recording-setup:
    ./recording-setup/setup.sh

# Record demo with background music (VM only)
record-demo:
    @echo "Generating voice clips (if needed)..."
    {{venv}}/bin/python scripts/generate_voice_clips.py
    @echo "Recording demo (with background music)..."
    ./recording-setup/record-demo.sh

# Record demo without background music
record-demo-no-music:
    @echo "Generating voice clips (if needed)..."
    {{venv}}/bin/python scripts/generate_voice_clips.py
    @echo "Recording demo (no background music)..."
    PURPLE_NO_MUSIC=1 ./recording-setup/record-demo.sh

# Record the everything walkthrough footage (voiceover added later, no music)
record-everything:
    @echo "Generating voice clips (if needed)..."
    PURPLE_DEMO_COMPOSITION=everything.json {{venv}}/bin/python scripts/generate_voice_clips.py
    @echo "Recording everything walkthrough footage..."
    PURPLE_NO_MUSIC=1 PURPLE_DEMO_COMPOSITION=everything.json PURPLE_RECORD_NO_POSTFX=1 \
        ./recording-setup/record-demo.sh recordings/everything.mp4 420

# Record the ad screen footage (no music; add your own in the editor)
record-ad:
    @echo "Generating voice clips (if needed)..."
    PURPLE_DEMO_COMPOSITION=ad.json {{venv}}/bin/python scripts/generate_voice_clips.py
    @echo "Recording ad screen footage..."
    @rm -f recordings/ad_zoom_events.json
    PURPLE_NO_MUSIC=1 PURPLE_DEMO_COMPOSITION=ad.json \
        PURPLE_ZOOM_EVENTS_FILE="$(pwd)/recordings/ad_zoom_events.json" \
        ./recording-setup/record-demo.sh recordings/ad.mp4 60

# Record the short ad screen footage (Play + Art beats; no music)
record-short-ad:
    @echo "Generating voice clips (if needed)..."
    PURPLE_DEMO_COMPOSITION=short_ad.json {{venv}}/bin/python scripts/generate_voice_clips.py
    @echo "Recording short ad screen footage..."
    @rm -f recordings/short_ad_zoom_events.json
    PURPLE_NO_MUSIC=1 PURPLE_DEMO_COMPOSITION=short_ad.json \
        PURPLE_ZOOM_EVENTS_FILE="$(pwd)/recordings/short_ad_zoom_events.json" \
        ./recording-setup/record-demo.sh recordings/short_ad.mp4 60

# Record the "Available now!" Art-room beat (no music, no voice)
record-available-now:
    @echo "Recording Available-now Art beat..."
    @rm -f recordings/available_now_zoom_events.json
    PURPLE_NO_MUSIC=1 PURPLE_DEMO_COMPOSITION=available_now.json \
        PURPLE_ZOOM_EVENTS_FILE="$(pwd)/recordings/available_now_zoom_events.json" \
        ./recording-setup/record-demo.sh recordings/available_now.mp4 30

# Record while you drive Purple yourself (no music, no scripted demo; stops on exit or after 5 min)
record-manual:
    @echo "Recording (manual, no music)... exit Purple to end, or it stops after 5 minutes."
    PURPLE_NO_MUSIC=1 PURPLE_RECORD_MANUAL=1 ./recording-setup/record-demo.sh

# Record 5s test clip (for testing recording pipeline)
record-demo-test:
    ./recording-setup/record-demo.sh recordings/demo-test.mp4 5

# Generate TTS voice clips for demo
voice-clips *args:
    @echo "Generating TTS voice clips for demo..."
    {{venv}}/bin/python scripts/generate_voice_clips.py {{args}}

# Generate 5 variants of each clip (for auditioning)
voice-variants:
    @echo "Generating 5 variants of each voice clip..."
    {{venv}}/bin/python scripts/generate_voice_clips.py --variants 5
    @echo ""
    @echo "Listen to variants and copy the best one over the original."

# Generate letter/number name clips for Music Room
letter-clips *args:
    @echo "Generating letter/number name clips for Music Room..."
    {{venv}}/bin/python scripts/generate_letter_clips.py {{args}}

# Verify deterministic TTS output
debug-tts:
    {{venv}}/bin/python scripts/debug_tts.py

# Clear cached TTS audio files
clear-tts-cache:
    {{venv}}/bin/python -c "from purple_tui.tts import clear_cache; n = clear_cache(); print(f'Cleared {n} cached TTS files')"

# Apply zoom keyframes to demo video
apply-zoom:
    {{venv}}/bin/python recording-setup/apply_zoom.py recordings/demo_cropped.mp4 recording-setup/zoom_events.json recordings/demo_zoomed.mp4

# Open zoom keyframe editor in browser
zoom-editor:
    python recording-setup/zoom_editor_server.py

# Test code split-screen POC (font resize proof of concept)
code-split-poc:
    PURPLE_ALACRITTY_CONFIG=config/alacritty/alacritty-dev.toml alacritty --config-file config/alacritty/alacritty-dev.toml -e {{venv}}/bin/python scripts/code_split_poc.py

# Release ISOs to Cloudflare R2 (e.g., just release, just release v1.0)
release *args:
    ./build-scripts/release-iso.sh {{args}}

# Upload the card PDFs to Cloudflare R2 (the files host)
upload-pdfs:
    ./build-scripts/upload-pdfs.sh

# Add print bleed to the postcard PDF for Vistaprint (cards/purple.pdf -> cards/purple-bleed.pdf)
print-card *args:
    @{{venv}}/bin/python cards/add_bleed.py {{args}}

# Delete old releases from Cloudflare R2, keeping only the current version
clean-releases *args:
    ./build-scripts/clean-old-releases.sh {{args}}

# Delete local ISOs older than N days (default: 7). E.g., just clean-isos 3, just clean-isos --dry-run
clean-isos *args:
    ./build-scripts/clean-old-isos.sh {{args}}

# Build the installer ISOs in Docker (standard + debug; PURPLE_WITH_BACKUP_ISO=1 adds the with-backup variant)
build *args:
    ./build-scripts/build-in-docker.sh {{args}}

# Flash ISO to USB drive (asks which of the newest build's ISOs to use)
flash *args:
    ./build-scripts/flash-to-usb.sh {{args}}

# Make a deliberately corrupted ISO copy to test the install's backup-image fallback: just corrupt-test-iso [iso] [primary|backup|both|merge|all] (default: newest with-backup ISO)
corrupt-test-iso *args:
    ./build-scripts/make-corrupt-test-iso.sh {{args}}

# Flash the newest corrupt-test ISO (made by just corrupt-test-iso)
flash-corrupt *args:
    ./build-scripts/flash-to-usb.sh --corrupt {{args}}

# Flash every corrupt-test scenario to plugged-in whitelisted drives, one per drive, then identify each stick as you unplug it
flash-corrupt-all *args:
    ./build-scripts/flash-all.sh --corrupt {{args}}

# Flash debug ISO to USB drive
flash-debug *args:
    ./build-scripts/flash-to-usb.sh --debug {{args}}

# Refresh udev after an aborted/ejected flash so a re-plugged drive is seen again
flash-clean:
    ./build-scripts/flash-clean.sh

# Flash ISO to ALL whitelisted USB drives in parallel
flash-all *args:
    ./build-scripts/flash-all.sh {{args}}

# Manually record a flashed build into the orders app (backfill a batch): just record-flash <commit> [drives] [flashed_at]
record-flash *args:
    ./build-scripts/record-flash.sh {{args}}

# Flash the cached stock Ubuntu ISO (for isolating Purple vs kernel issues on target hardware)
flash-ubuntu *args:
    ./build-scripts/flash-to-usb.sh {{args}} /opt/purple-installer/build/ubuntu-24.04.1-live-server-amd64.iso

# AI UX testing: let a Claude agent explore the app as a simulated kid
ux *args:
    @PYTHONPATH={{justfile_directory()}} {{venv}}/bin/python scripts/ai_ux_runner.py {{args}}

# AI UX bug hunt: autonomous budget-aware bug hunting (default $10)
hunt *args:
    @PYTHONPATH={{justfile_directory()}} {{venv}}/bin/python scripts/ai_ux_hunt.py {{args}}

# Run Python with venv (e.g., just python script.py, just python -c 'print(1)')
python *args:
    @PYTHONPATH={{justfile_directory()}} {{venv}}/bin/python3 {{args}}

# Run Python from stdin (e.g., echo 'print("hi")' | just pystdin)
pystdin:
    @{{venv}}/bin/python -
