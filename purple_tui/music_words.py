"""Word recognition for Music Mode Letters mode.

After a replay finishes, if the typed letters form a known word, the word
is spoken aloud via TTS. This connects individual letter sounds to whole words.

Pure logic with no UI, audio, or pygame dependencies. Kept separate from
music_room.py so it's easy to test.
"""

from .music_session import MODE_LETTERS

# Basic words for kids 4-7. All lowercase, 2-5 letters.
WORDS = frozenset({
    # Animals
    "cat", "dog", "pig", "cow", "hen", "bat", "bug", "ant", "bee", "fox",
    "owl", "rat", "ram", "emu", "yak", "fish", "frog", "duck", "bird",
    "bear", "deer", "goat", "lamb", "lion", "seal", "wolf",
    # Family
    "mom", "dad", "sis", "bro", "baby", "nana",
    # Body
    "arm", "ear", "eye", "leg", "toe", "lip", "rib", "chin", "hand",
    "head", "knee", "neck", "nose", "back", "face", "foot", "hair",
    # Colors
    "red", "blue", "pink", "gold",
    # Nature
    "sun", "sky", "sea", "mud", "log", "rock", "rain", "snow", "wind",
    "leaf", "tree", "star", "moon",
    # Food
    "pie", "jam", "egg", "ham", "nut", "pea", "yam", "cake", "corn",
    "milk", "rice", "soup",
    # Objects
    "bag", "bed", "box", "bus", "cap", "car", "cup", "fan", "hat",
    "jar", "key", "map", "mug", "pan", "pen", "pin", "pot", "rug",
    "top", "toy", "van", "ball", "bell", "bike", "boat", "book",
    "bowl", "coat", "door", "drum", "flag", "fork", "game", "gift",
    "kite", "lamp", "lock", "ring", "rope", "shoe", "sock", "song",
    "tent", "wall",
    # Descriptors
    "big", "hot", "new", "old", "wet", "cold", "cool", "fast", "good",
    "kind", "long", "loud", "nice", "safe", "slow", "soft", "tall",
    "tiny", "warm", "wide",
    # Actions
    "eat", "hop", "hug", "nap", "run", "sit", "dig", "fly", "mix",
    "cry", "clap", "draw", "dump", "find", "give", "help", "hide",
    "jump", "kick", "kiss", "lick", "look", "love", "make", "move",
    "open", "play", "pull", "push", "read", "ride", "roll", "sing",
    "skip", "spin", "stop", "swim", "talk", "turn", "walk", "wash",
    "wave", "wink", "wish", "work",
    # Common words
    "and", "the", "for", "fun", "day", "yes", "wow", "yay", "go",
    "hi", "no", "up",
})


def extract_word(replay_data: list[tuple[str, str, float]], letters_mode: str = MODE_LETTERS) -> str | None:
    """Extract a recognized word from replay data.

    Filters to letter-mode alphabetic keys, joins them, and checks
    against the known word list.

    Args:
        replay_data: List of (key, mode, delay) triples from MusicSession.
        letters_mode: The mode string for letters (default MODE_LETTERS).

    Returns:
        The recognized word (lowercase) if found, else None.
    """
    letters = []
    for key, mode, _delay in replay_data:
        if mode == letters_mode and key.isalpha():
            letters.append(key.lower())

    if not letters:
        return None

    word = "".join(letters)
    if word in WORDS:
        return word
    return None
