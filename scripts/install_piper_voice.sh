#!/bin/bash
# Install the speech voices: Piper (Natural) to ~/.local/share/piper-voices/ and
# flite (Quick) to ~/.local/share/flite-voices/, skipping any already present.
# Can be run standalone or called from setup_dev.sh.

set -e

# Colors (only define if not already set by caller)
GREEN="${GREEN:-\033[0;32m}"
YELLOW="${YELLOW:-\033[1;33m}"
BLUE="${BLUE:-\033[0;34m}"
NC="${NC:-\033[0m}"

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

echo_step "Setting up Piper TTS voice..."
PIPER_VOICES_DIR="$HOME/.local/share/piper-voices"
VOICE_MODEL="en_US-libritts_r-medium"
if [ -f "$PIPER_VOICES_DIR/$VOICE_MODEL.onnx" ]; then
    echo_info "✓ Piper voice model already downloaded"
else
    mkdir -p "$PIPER_VOICES_DIR"
    echo_info "Downloading Piper voice model ($VOICE_MODEL)..."
    # Download from Hugging Face
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium/$VOICE_MODEL.onnx" -o "$PIPER_VOICES_DIR/$VOICE_MODEL.onnx"
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium/$VOICE_MODEL.onnx.json" -o "$PIPER_VOICES_DIR/$VOICE_MODEL.onnx.json"
    if [ -f "$PIPER_VOICES_DIR/$VOICE_MODEL.onnx" ]; then
        echo_info "✓ Piper voice model downloaded"
    else
        echo_warn "Could not download Piper voice model (TTS may not work)"
    fi
fi

echo_step "Setting up the flite voice (the Quick voice)..."
FLITE_VOICES_DIR="$HOME/.local/share/flite-voices"
FLITE_VOICE="cmu_us_lnh"
if [ -f "$FLITE_VOICES_DIR/$FLITE_VOICE.flitevox" ]; then
    echo_info "✓ flite voice already downloaded"
else
    mkdir -p "$FLITE_VOICES_DIR"
    curl -L "http://festvox.org/flite/packed/flite-2.3/voices/$FLITE_VOICE.flitevox" -o "$FLITE_VOICES_DIR/$FLITE_VOICE.flitevox" \
        || echo_warn "Could not download the flite voice (the Quick voice will not work)"
fi
command -v flite >/dev/null 2>&1 || echo_warn "flite is not installed (apt install flite); the Quick voice needs it"
