# Purple's English voice: Piper's libritts_r medium with its noise fixed (scripts/steady_voice.py),
# hosted on R2. Sourced by the image build, the Chromebook bundle and dev setup; scripts/studio_bundle.py
# reads the same lines. A new model goes up under a new folder, with its hashes here.
VOICE_EN=en_US-libritts_r-medium
VOICE_EN_BASE=https://files.purplecomputer.org/voices/steady-d9c5268d
VOICE_EN_SHA256=d9c5268db8621266a4b8a63dd3cb12ad2cfa4fc25b044764f943c9a9c7320004
VOICE_EN_JSON_SHA256=b471dc60d2d8335e819c393d196d6fbf792817f40051257b269878505bc9afb3
# Studio's copy: the same model with float16 weights (steady_voice.py --half).
VOICE_EN_HALF_SHA256=db8dad84562b33c94fa63c6ab9a01a3774441036b05a41c54cdabb5c20720598

_voice_sha256() { { sha256sum "$1" 2>/dev/null || shasum -a 256 "$1"; } | cut -d' ' -f1; }

# fetch_en_voice <dir>: the model and its config into dir, replacing any copy that isn't this one.
fetch_en_voice() {
    local dir=$1 name sha
    mkdir -p "$dir"
    for name in "$VOICE_EN.onnx:$VOICE_EN_SHA256" "$VOICE_EN.onnx.json:$VOICE_EN_JSON_SHA256"; do
        sha=${name#*:} name=${name%%:*}
        [ -f "$dir/$name" ] && [ "$(_voice_sha256 "$dir/$name")" = "$sha" ] && continue
        curl -fsSL "$VOICE_EN_BASE/$name" -o "$dir/$name.part"
        [ "$(_voice_sha256 "$dir/$name.part")" = "$sha" ] || { echo "$name doesn't match its pinned hash" >&2; rm -f "$dir/$name.part"; return 1; }
        mv "$dir/$name.part" "$dir/$name"
    done
}
