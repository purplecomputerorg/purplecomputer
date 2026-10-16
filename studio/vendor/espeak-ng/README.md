# espeak-ng for Studio's voice

Studio's Purple speaks with Piper, as Purple does. Piper turns text into phonemes with espeak-ng, so this is espeak-ng compiled to WebAssembly: the same commit piper-tts 1.4.1 builds against (`212928b`), with a small bridge (`espeak_bridge.c`) making the same calls as piper's `espeakbridge.c`. The English data it reads at runtime comes from the installed piper package (`scripts/studio_bundle.py`).

`espeak.mjs` and `espeak.wasm` are built from source by `build.sh`; run it again after changing the bridge or the commit.

**License.** espeak-ng is GPL-3.0-or-later, and so are these files and the bridge. Source: https://github.com/espeak-ng/espeak-ng/tree/212928b394a96e8fd2096616bfd54e17845c48f6, plus `espeak_bridge.c` and `build.sh` here. Studio's pages link to this source wherever the voice is served.
