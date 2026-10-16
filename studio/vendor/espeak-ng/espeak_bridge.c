// SPDX-License-Identifier: GPL-3.0-or-later
// The same espeak-ng calls as piper1-gpl's espeakbridge.c, for emscripten.
// phonemize() returns one line per clause: phonemes \t terminator flags.
#include <espeak-ng/speak_lib.h>
#include <emscripten/emscripten.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char *out = NULL;

EMSCRIPTEN_KEEPALIVE int init(const char *data_dir, const char *voice) {
    if (espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, data_dir, 0) < 0) return -1;
    return espeak_SetVoiceByName(voice) == EE_OK ? 0 : -2;
}

EMSCRIPTEN_KEEPALIVE const char *phonemize(const char *text) {
    size_t cap = 256, len = 0;
    free(out);
    out = malloc(cap);
    out[0] = 0;
    while (text != NULL) {
        int terminator = 0;
        const char *ph = espeak_TextToPhonemesWithTerminator((const void **)&text, espeakCHARS_AUTO, espeakPHONEMES_IPA, &terminator);
        size_t need = len + strlen(ph ? ph : "") + 16;
        if (need > cap) { cap = need * 2; out = realloc(out, cap); }
        len += sprintf(out + len, "%s\t%d\n", ph ? ph : "", terminator & 0x000FFFFF);
    }
    return out;
}
