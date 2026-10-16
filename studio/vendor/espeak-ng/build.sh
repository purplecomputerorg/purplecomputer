#!/usr/bin/env bash
# Rebuilds espeak.mjs and espeak.wasm: espeak-ng at the commit piper-tts 1.4.1 pins, plus espeak_bridge.c.
# Needs emcc (emsdk 4.0) on PATH. usage: vendor/espeak-ng/build.sh
set -euo pipefail
COMMIT=212928b394a96e8fd2096616bfd54e17845c48f6
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
curl -fsSL "https://github.com/espeak-ng/espeak-ng/archive/$COMMIT.tar.gz" | tar xz -C "$WORK"
SRC=$WORK/espeak-ng-$COMMIT
mkdir -p "$WORK/include"
printf '#define HAVE_MKSTEMP 1\n#define USE_ASYNC 0\n#define USE_KLATT 0\n#define USE_LIBPCAUDIO 0\n#define USE_LIBSONIC 0\n#define USE_MBROLA 0\n#define USE_SPEECHPLAYER 0\n#define PACKAGE_VERSION "1.52.0.1"\n' > "$WORK/include/config.h"
FILES=()
for f in common mnemonics error ieee80 compiledata compiledict dictionary encoding intonation langopts numbers phoneme phonemelist readclause setlengths soundicon spect ssml synthdata synthesize tr_languages translate translateword voices wavegen speech espeak_api; do FILES+=("$SRC/src/libespeak-ng/$f.c"); done
for f in case categories ctype proplist scripts tostring; do FILES+=("$SRC/src/ucd-tools/src/$f.c"); done
emcc -O3 -fwrapv -w -DLIBESPEAK_NG_EXPORT=1 '-DPATH_ESPEAK_DATA="/espeak-ng-data"' \
  -I"$WORK/include" -I"$SRC/src/include" -I"$SRC/src/libespeak-ng" -I"$SRC/src/ucd-tools/src/include" \
  "${FILES[@]}" "$HERE/espeak_bridge.c" \
  -sMODULARIZE=1 -sEXPORT_ES6=1 -sEXPORT_NAME=createEspeak -sENVIRONMENT=web,worker -sALLOW_MEMORY_GROWTH=1 \
  -sFORCE_FILESYSTEM=1 -sEXPORTED_FUNCTIONS=_init,_phonemize -sEXPORTED_RUNTIME_METHODS=ccall,FS \
  -o "$HERE/espeak.mjs"
