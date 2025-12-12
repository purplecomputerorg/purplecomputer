"""
Content API for Purple Computer

Provides a stable interface for modes to access content from purplepacks:
- Emojis (with synonyms)
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

            # Synonyms (same emoji, different words)
            "kitty": "🐱", "kitten": "🐱", "meow": "🐱",
            "puppy": "🐶", "doggy": "🐶", "woof": "🐶",
            "bunny": "🐰", "horsie": "🐴",
            "dino": "🦕", "rex": "🦖", "t-rex": "🦖",
            "birdie": "🐦", "fishy": "🐟",
            "sunny": "☀️", "moony": "🌙", "starry": "⭐",
            "rainy": "🌧️", "snowy": "❄️", "cloudy": "☁️",
            "yummy": "🍦", "treat": "🍬",
            "smile": "😊", "cry": "😢", "giggle": "😂",
            "haha": "😂", "lol": "😂",
            "good": "✅", "bad": "❌", "great": "👍",
            "yay": "👏", "hi": "👋", "hello": "👋", "bye": "👋",
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
        elif pack_type == "sounds":
            self._load_sounds_pack(content_dir, pack_dir)

    def _load_emoji_pack(self, content_dir: Path) -> None:
        """Load emoji pack - simple word -> emoji mapping"""
        emoji_file = content_dir / "emoji.json"
        if emoji_file.exists():
            try:
                with open(emoji_file) as f:
                    data = json.load(f)
                    self.emojis.update(data)
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
        """Get emoji for a word"""
        word = word.lower().strip()
        return self.emojis.get(word)

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

        for word, emoji in self.emojis.items():
            if word.startswith(prefix):
                results.append((word, emoji))

        return sorted(results, key=lambda x: x[0])


# Global content manager instance
_content: Optional[ContentManager] = None


def get_content() -> ContentManager:
    """Get the global content manager"""
    global _content
    if _content is None:
        _content = ContentManager()
        _content.load_all()
    return _content
