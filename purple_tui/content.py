"""
Content API for Purple Computer

Provides a stable interface for modes to access content from purplepacks:
- Emojis (with synonyms)
- Definitions (word meanings)
- Stories (text + audio)
- Sounds (audio files)

Purplepacks are content-only (JSON + assets) - NO executable Python code.
"""

import json
from pathlib import Path
from typing import Optional


class ContentManager:
    """
    Manages loading and accessing content from purplepacks.

    Purplepacks are stored in ~/.purple/packs/ and contain:
    - manifest.json (pack metadata)
    - content/ directory with JSON and asset files
    """

    def __init__(self, packs_dir: Optional[Path] = None):
        self.packs_dir = packs_dir or Path.home() / ".purple" / "packs"
        self.emojis: dict[str, str] = {}           # word -> emoji
        self.synonyms: dict[str, str] = {}         # synonym -> canonical word
        self.definitions: dict[str, str] = {}      # word -> definition
        self.sounds: dict[str, Path] = {}          # sound_id -> file path
        self._loaded = False

    def load_all(self) -> None:
        """Load content from all installed packs"""
        if self._loaded:
            return

        # Load built-in defaults first
        self._load_defaults()

        # Then load from installed packs
        if self.packs_dir.exists():
            for pack_dir in self.packs_dir.iterdir():
                if pack_dir.is_dir():
                    self._load_pack(pack_dir)

        self._loaded = True

    def _load_defaults(self) -> None:
        """Load default emojis and definitions"""
        # Default emojis - ~100 kid-friendly options
        self.emojis = {
            # Animals
            "cat": "🐱", "dog": "🐶", "elephant": "🐘", "lion": "🦁",
            "tiger": "🐯", "bear": "🐻", "panda": "🐼", "koala": "🐨",
            "pig": "🐷", "cow": "🐮", "horse": "🐴", "unicorn": "🦄",
            "rabbit": "🐰", "mouse": "🐭", "hamster": "🐹", "fox": "🦊",
            "monkey": "🐵", "chicken": "🐔", "penguin": "🐧", "bird": "🐦",
            "duck": "🦆", "owl": "🦉", "frog": "🐸", "turtle": "🐢",
            "snake": "🐍", "dinosaur": "🦕", "trex": "🦖", "whale": "🐋",
            "dolphin": "🐬", "fish": "🐟", "octopus": "🐙", "butterfly": "🦋",
            "bee": "🐝", "ladybug": "🐞", "snail": "🐌", "crab": "🦀",

            # Nature
            "sun": "☀️", "moon": "🌙", "star": "⭐", "rainbow": "🌈",
            "cloud": "☁️", "rain": "🌧️", "snow": "❄️", "flower": "🌸",
            "tree": "🌲", "plant": "🌱", "leaf": "🍃", "mushroom": "🍄",

            # Food
            "apple": "🍎", "banana": "🍌", "orange": "🍊", "grape": "🍇",
            "strawberry": "🍓", "watermelon": "🍉", "pizza": "🍕",
            "icecream": "🍦", "cake": "🎂", "cookie": "🍪", "candy": "🍬",
            "chocolate": "🍫", "bread": "🍞", "cheese": "🧀",

            # Objects
            "heart": "❤️", "star": "⭐", "ball": "⚽", "balloon": "🎈",
            "gift": "🎁", "book": "📚", "pencil": "✏️", "crayon": "🖍️",
            "art": "🎨", "music": "🎵", "drum": "🥁", "guitar": "🎸",
            "piano": "🎹", "rocket": "🚀", "car": "🚗", "bus": "🚌",
            "train": "🚂", "airplane": "✈️", "boat": "⛵", "bike": "🚲",
            "house": "🏠", "castle": "🏰", "tent": "⛺",

            # Faces/expressions
            "happy": "😊", "sad": "😢", "laugh": "😂", "love": "😍",
            "cool": "😎", "silly": "🤪", "sleepy": "😴", "surprised": "😮",
            "think": "🤔", "wow": "🤩",

            # Activities
            "run": "🏃", "swim": "🏊", "dance": "💃", "sing": "🎤",
            "play": "🎮", "read": "📖", "write": "✍️", "paint": "🖌️",

            # Misc
            "yes": "✅", "no": "❌", "thumbsup": "👍", "clap": "👏",
            "wave": "👋", "hug": "🤗", "fire": "🔥", "sparkle": "✨",
            "magic": "🪄", "crown": "👑", "gem": "💎",
        }

        # Synonyms map to canonical emoji names
        self.synonyms = {
            # Animal synonyms
            "kitty": "cat", "kitten": "cat", "meow": "cat",
            "puppy": "dog", "doggy": "dog", "woof": "dog",
            "bunny": "rabbit", "horsie": "horse",
            "dino": "dinosaur", "rex": "trex", "t-rex": "trex",
            "birdie": "bird", "fishy": "fish",

            # Nature synonyms
            "sunny": "sun", "moony": "moon", "starry": "star",
            "rainy": "rain", "snowy": "snow", "cloudy": "cloud",

            # Food synonyms
            "yummy": "icecream", "treat": "candy",

            # Expression synonyms
            "smile": "happy", "cry": "sad", "giggle": "laugh",
            "haha": "laugh", "lol": "laugh",

            # Misc synonyms
            "good": "yes", "bad": "no", "great": "thumbsup",
            "yay": "clap", "hi": "wave", "hello": "wave", "bye": "wave",
        }

        # Default definitions
        self.definitions = {
            "cat": "A small furry animal that says meow",
            "dog": "A friendly animal that says woof and loves to play",
            "elephant": "A very big gray animal with a long trunk",
            "sun": "The big bright ball in the sky that gives us light",
            "moon": "The round light we see in the night sky",
            "rainbow": "Colorful stripes in the sky after rain",
            "apple": "A round red or green fruit that grows on trees",
            "happy": "Feeling good and joyful inside",
            "love": "A warm feeling when you care about someone",
        }

    def _load_pack(self, pack_dir: Path) -> None:
        """Load content from a single pack directory"""
        manifest_path = pack_dir / "manifest.json"
        if not manifest_path.exists():
            return

        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        pack_type = manifest.get("type", "")
        content_dir = pack_dir / "content"

        if pack_type == "emoji":
            self._load_emoji_pack(content_dir)
        elif pack_type == "definitions":
            self._load_definitions_pack(content_dir)
        elif pack_type == "sounds":
            self._load_sounds_pack(content_dir, pack_dir)

    def _load_emoji_pack(self, content_dir: Path) -> None:
        """Load emoji definitions from pack"""
        emoji_file = content_dir / "emoji.json"
        if emoji_file.exists():
            try:
                with open(emoji_file) as f:
                    data = json.load(f)
                    self.emojis.update(data)
            except (json.JSONDecodeError, OSError):
                pass

        synonyms_file = content_dir / "synonyms.json"
        if synonyms_file.exists():
            try:
                with open(synonyms_file) as f:
                    data = json.load(f)
                    self.synonyms.update(data)
            except (json.JSONDecodeError, OSError):
                pass

    def _load_definitions_pack(self, content_dir: Path) -> None:
        """Load word definitions from pack"""
        defs_file = content_dir / "definitions.json"
        if defs_file.exists():
            try:
                with open(defs_file) as f:
                    data = json.load(f)
                    self.definitions.update(data)
            except (json.JSONDecodeError, OSError):
                pass

    def _load_sounds_pack(self, content_dir: Path, pack_dir: Path) -> None:
        """Load sound file references from pack"""
        sounds_file = content_dir / "sounds.json"
        if sounds_file.exists():
            try:
                with open(sounds_file) as f:
                    data = json.load(f)
                    for sound_id, filename in data.items():
                        sound_path = pack_dir / "assets" / filename
                        if sound_path.exists():
                            self.sounds[sound_id] = sound_path
            except (json.JSONDecodeError, OSError):
                pass

    # Public API for modes

    def get_emoji(self, word: str) -> Optional[str]:
        """Get emoji for a word (checks synonyms too)"""
        word = word.lower().strip()

        # Direct match
        if word in self.emojis:
            return self.emojis[word]

        # Check synonyms
        canonical = self.synonyms.get(word)
        if canonical and canonical in self.emojis:
            return self.emojis[canonical]

        return None

    def get_definition(self, word: str) -> Optional[str]:
        """Get definition for a word"""
        word = word.lower().strip()
        return self.definitions.get(word)

    def get_sound(self, sound_id: str) -> Optional[Path]:
        """Get path to a sound file"""
        return self.sounds.get(sound_id)

    def list_emojis(self) -> list[str]:
        """Get list of all available emoji words"""
        return sorted(self.emojis.keys())

    def search_emojis(self, prefix: str) -> list[tuple[str, str]]:
        """Search for emojis starting with prefix, returns [(word, emoji), ...]"""
        prefix = prefix.lower()
        results = []

        # Search direct matches
        for word, emoji in self.emojis.items():
            if word.startswith(prefix):
                results.append((word, emoji))

        # Search synonyms
        for synonym, canonical in self.synonyms.items():
            if synonym.startswith(prefix) and canonical in self.emojis:
                results.append((synonym, self.emojis[canonical]))

        return sorted(set(results), key=lambda x: x[0])


# Global content manager instance
_content: Optional[ContentManager] = None


def get_content() -> ContentManager:
    """Get the global content manager"""
    global _content
    if _content is None:
        _content = ContentManager()
        _content.load_all()
    return _content
