"""Secret family-menu unlock.

Holding Ctrl and typing a family codeword (released as one run) flips a
persistent flag that reveals a hidden "Secret Menu" in the parent menu.

The ISO ships to everyone, so only SHA-256 hashes of the codewords live here,
never the plaintext: grepping the image reveals nothing. The codeword length
is not secret, so hashes are grouped by length to keep matching cheap.

Add a family member: run this module to print a hash, then drop it into the
right length bucket below.

    python -m purple_tui.secret lily
"""

import hashlib
from collections import deque

# length -> {sha256(codeword) for codewords of that length}
_HASHES_BY_LEN: dict[int, set[str]] = {
    3: {"d2efaa6dd6ae6136c19944fae329efd3fb2babe1e6eec26982a422aa60d222b8"},  # ari
    4: {"40903c59d19feef1d67c455499304c194ebdec82df78790c3ceaac92bd1d84be"},  # lily
}

_MAX_LEN = max(_HASHES_BY_LEN, default=0)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class SecretKnock:
    """Detects the Ctrl-held codeword gesture from the character stream.

    Feed every CharacterAction. Ctrl-held letters accumulate; any character
    typed without Ctrl clears the buffer, so the codeword must be typed in a
    single Ctrl hold. Returns True the moment the buffer ends with a codeword.
    """

    def __init__(self) -> None:
        self._buf: deque[str] = deque(maxlen=_MAX_LEN)

    def feed(self, action) -> bool:
        from .keyboard import CharacterAction
        if not isinstance(action, CharacterAction):
            return False
        if not action.ctrl_held:
            self._buf.clear()
            return False
        if action.is_repeat or not action.char.isalpha():
            return False
        self._buf.append(action.char.lower())
        tail = "".join(self._buf)
        for length, hashes in _HASHES_BY_LEN.items():
            if len(tail) >= length and _hash(tail[-length:]) in hashes:
                self._buf.clear()
                return True
        return False


if __name__ == "__main__":
    import sys
    for word in sys.argv[1:]:
        w = word.lower()
        print(f"{len(w)}: {_hash(w)}  # {w}")
