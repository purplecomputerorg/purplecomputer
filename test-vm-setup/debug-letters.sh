#!/bin/bash
# Show which clip Music's Say Letters plays for each key, as `run` (scripts/run_local.sh) sees it. Pass a repo path to override the default.
set -e

cd "${1:-$HOME/purplecomputer}"
echo "Checkout: $(pwd) at $(git log --oneline -1)"
git status --short --ignored packs/core-sounds/content/letters
echo

# run_local.sh runs with HOME at .test_home, so its packs and settings live there.
HOME="$(pwd)/.test_home" PYTHONPATH="$(pwd)" python3 - <<'EOF'
import hashlib, json, string
from pathlib import Path
from purple_tui.content import get_content

core = Path("packs/core-sounds/content/letters")
dirs = get_content().pack_dirs("letters") + [core]
print("Searched, first hit wins:", *dirs, sep="\n  ")
settings = Path.home() / ".purple" / "settings.json"
print("kid_letters (Textual UI only):", json.loads(settings.read_text()).get("kid_letters") if settings.exists() else "no settings file")
print()
for key in string.ascii_lowercase + string.digits:
    clip = next((p for d in dirs for ext in (".ogg", ".wav") if (p := d / f"{key}{ext}").exists()), None)
    print(key, clip, hashlib.md5(clip.read_bytes()).hexdigest()[:8] if clip else "")
EOF
