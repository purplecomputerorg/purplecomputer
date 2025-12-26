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
        self.colors: dict[str, str] = {}           # color name -> hex code
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
        # Default emojis - kid-friendly options
        self.emojis = {
            # Animals - common
            "cat": "🐱", "dog": "🐶", "elephant": "🐘", "lion": "🦁",
            "tiger": "🐯", "bear": "🐻", "panda": "🐼", "koala": "🐨",
            "pig": "🐷", "cow": "🐮", "horse": "🐴", "unicorn": "🦄",
            "rabbit": "🐰", "mouse": "🐭", "hamster": "🐹", "fox": "🦊",
            "monkey": "🐵", "chicken": "🐔", "penguin": "🐧", "bird": "🐦",
            "duck": "🦆", "owl": "🦉", "frog": "🐸", "turtle": "🐢",
            "snake": "🐍", "dinosaur": "🦕", "trex": "🦖", "whale": "🐋",
            "dolphin": "🐬", "fish": "🐟", "octopus": "🐙", "butterfly": "🦋",
            "bee": "🐝", "ladybug": "🐞", "snail": "🐌", "crab": "🦀",

            # Animals - more
            "zebra": "🦓", "giraffe": "🦒", "hippo": "🦛", "gorilla": "🦍",
            "wolf": "🐺", "deer": "🦌", "sheep": "🐑", "goat": "🐐",
            "camel": "🐪", "kangaroo": "🦘", "sloth": "🦥", "hedgehog": "🦔",
            "raccoon": "🦝", "squirrel": "🐿️", "bat": "🦇", "seal": "🦭",
            "shark": "🦈", "jellyfish": "🪼", "starfish": "⭐", "shrimp": "🦐",
            "lobster": "🦞", "squid": "🦑", "ant": "🐜", "spider": "🕷️",
            "scorpion": "🦂", "mosquito": "🦟", "cricket": "🦗", "worm": "🪱",
            "parrot": "🦜", "flamingo": "🦩", "peacock": "🦚", "swan": "🦢",
            "rooster": "🐓", "turkey": "🦃", "eagle": "🦅", "dove": "🕊️",
            "crocodile": "🐊", "lizard": "🦎", "dragon": "🐉",

            # Fantasy/magical
            "fairy": "🧚", "mermaid": "🧜", "wizard": "🧙", "genie": "🧞",
            "ghost": "👻", "alien": "👽", "robot": "🤖", "monster": "👾",
            "vampire": "🧛", "zombie": "🧟", "ogre": "👹", "troll": "🧌",

            # Nature
            "sun": "☀️", "moon": "🌙", "star": "⭐", "rainbow": "🌈",
            "cloud": "☁️", "rain": "🌧️", "snow": "❄️", "flower": "🌸",
            "tree": "🌲", "plant": "🌱", "leaf": "🍃", "mushroom": "🍄",
            "rose": "🌹", "sunflower": "🌻", "tulip": "🌷", "blossom": "🌼",
            "mountain": "⛰️", "volcano": "🌋", "beach": "🏖️", "island": "🏝️",
            "ocean": "🌊", "desert": "🏜️", "forest": "🌳", "cactus": "🌵",

            # Food - fruits
            "apple": "🍎", "banana": "🍌", "orange": "🍊", "grape": "🍇",
            "strawberry": "🍓", "watermelon": "🍉", "peach": "🍑",
            "cherry": "🍒", "lemon": "🍋", "pineapple": "🍍", "coconut": "🥥",
            "mango": "🥭", "kiwi": "🥝", "blueberry": "🫐", "pear": "🍐",

            # Food - other
            "pizza": "🍕", "burger": "🍔", "hotdog": "🌭", "taco": "🌮",
            "fries": "🍟", "popcorn": "🍿", "pretzel": "🥨", "egg": "🥚",
            "bread": "🍞", "cheese": "🧀", "bacon": "🥓", "pancake": "🥞",
            "icecream": "🍦", "cake": "🎂", "cookie": "🍪", "candy": "🍬",
            "chocolate": "🍫", "donut": "🍩", "cupcake": "🧁", "pie": "🥧",
            "tomato": "🍅", "carrot": "🥕", "corn": "🌽", "broccoli": "🥦",
            "avocado": "🥑", "potato": "🥔", "onion": "🧅", "garlic": "🧄",
            "milk": "🥛", "juice": "🧃", "coffee": "☕", "tea": "🍵",

            # Objects
            "heart": "❤️", "ball": "⚽", "balloon": "🎈",
            "gift": "🎁", "book": "📚", "pencil": "✏️", "crayon": "🖍️",
            "art": "🎨", "music": "🎵", "drum": "🥁", "guitar": "🎸",
            "piano": "🎹", "rocket": "🚀", "car": "🚗", "bus": "🚌",
            "train": "🚂", "airplane": "✈️", "boat": "⛵", "bike": "🚲",
            "house": "🏠", "castle": "🏰", "tent": "⛺",
            "phone": "📱", "camera": "📷", "computer": "💻", "clock": "🕐",
            "lamp": "💡", "key": "🔑", "umbrella": "☂️", "glasses": "👓",
            "hat": "🎩", "shoe": "👟", "shirt": "👕", "dress": "👗",
            "backpack": "🎒", "scissors": "✂️", "hammer": "🔨", "wrench": "🔧",

            # Vehicles
            "helicopter": "🚁", "tractor": "🚜", "ambulance": "🚑",
            "firetruck": "🚒", "police": "🚓", "taxi": "🚕", "truck": "🚚",
            "scooter": "🛴", "motorcycle": "🏍️", "ship": "🚢", "canoe": "🛶",

            # Sports
            "soccer": "⚽", "basketball": "🏀", "football": "🏈",
            "baseball": "⚾", "tennis": "🎾", "bowling": "🎳", "golf": "⛳",
            "skating": "⛸️", "skiing": "⛷️", "surfing": "🏄", "fishing": "🎣",

            # Faces/expressions
            "happy": "😊", "sad": "😢", "laugh": "😂", "love": "😍",
            "cool": "😎", "silly": "🤪", "sleepy": "😴", "surprised": "😮",
            "think": "🤔", "wow": "🤩", "angry": "😠", "scared": "😨",
            "sick": "🤒", "dizzy": "😵", "nerd": "🤓", "party": "🥳",

            # Activities
            "run": "🏃", "swim": "🏊", "dance": "💃", "sing": "🎤",
            "play": "🎮", "read": "📖", "write": "✍️", "paint": "🖌️",

            # Misc
            "yes": "✅", "no": "❌", "thumbsup": "👍", "clap": "👏",
            "wave": "👋", "hug": "🤗", "fire": "🔥", "sparkle": "✨",
            "magic": "🪄", "crown": "👑", "gem": "💎", "medal": "🏅",
            "trophy": "🏆", "flag": "🚩", "bomb": "💣", "lightning": "⚡",
            "poop": "💩", "skull": "💀", "eye": "👁️", "brain": "🧠",

            # Holidays
            "pumpkin": "🎃", "snowman": "☃️", "santa": "🎅", "tree": "🎄",
            "present": "🎁", "firework": "🎆", "egg": "🥚", "bunny": "🐰",

            # Synonyms (same emoji, different words)
            "kitty": "🐱", "kitten": "🐱", "meow": "🐱",
            "puppy": "🐶", "doggy": "🐶", "woof": "🐶",
            "horsie": "🐴", "lamb": "🐑",
            "dino": "🦕", "tyrannosaurus": "🦖",
            "birdie": "🐦", "fishy": "🐟",
            "sunny": "☀️", "moony": "🌙", "starry": "⭐",
            "rainy": "🌧️", "snowy": "❄️", "cloudy": "☁️",
            "yummy": "🍦", "treat": "🍬",
            "smile": "😊", "cry": "😢", "giggle": "😂",
            "haha": "😂", "lol": "😂",
            "good": "✅", "bad": "❌", "great": "👍",
            "yay": "👏", "hi": "👋", "hello": "👋", "bye": "👋",
        }

        # Default colors for paint mixing (RYB primary/secondary + common colors)
        self.colors = {
            # Primary colors (paint)
            "red": "#E52B50",      # A true paint red (like cadmium red)
            "yellow": "#FFEB00",   # Primary yellow
            "blue": "#0047AB",     # Cobalt blue (paint blue)

            # Secondary colors (what you get from mixing primaries)
            "orange": "#FF6600",   # Red + Yellow
            "green": "#228B22",    # Yellow + Blue
            "purple": "#7B2D8E",   # Red + Blue
            "violet": "#7B2D8E",   # Same as purple

            # Tertiary and common colors
            "pink": "#FF69B4",
            "brown": "#8B4513",
            "black": "#1A1A1A",
            "white": "#F5F5F5",
            "gray": "#808080",
            "grey": "#808080",

            # Fun colors kids know
            "cyan": "#00FFFF",
            "magenta": "#FF00FF",
            "gold": "#FFD700",
            "silver": "#C0C0C0",
            "teal": "#008080",
            "turquoise": "#40E0D0",
            "coral": "#FF7F50",
            "salmon": "#FA8072",
            "peach": "#FFCBA4",
            "lavender": "#E6E6FA",
            "mint": "#98FF98",
            "lime": "#32CD32",
            "maroon": "#800000",
            "navy": "#000080",
            "olive": "#808000",
            "indigo": "#4B0082",
            "tan": "#D2B48C",
            "beige": "#F5F5DC",
            "cream": "#FFFDD0",
            "sky": "#87CEEB",
            "rose": "#FF007F",
            "crimson": "#DC143C",
            "scarlet": "#FF2400",
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

    def get_color(self, word: str) -> Optional[str]:
        """Get hex color code for a color name"""
        word = word.lower().strip()
        return self.colors.get(word)

    def search_colors(self, prefix: str) -> list[tuple[str, str]]:
        """Search for colors starting with prefix, returns [(name, hex), ...]"""
        prefix = prefix.lower()
        results = []

        for name, hex_code in self.colors.items():
            if name.startswith(prefix):
                results.append((name, hex_code))

        return sorted(results, key=lambda x: x[0])

    def list_colors(self) -> list[str]:
        """Get list of all available color names"""
        return sorted(self.colors.keys())

    def get_word(self, word: str) -> tuple[str, str] | None:
        """Get emoji or color for a word, including plural forms.

        Returns (value, type) where type is 'emoji' or 'color', or None if not found.
        For plurals like 'cats' or 'reds', returns the singular form.
        """
        word = word.lower().strip()

        # Check emoji first
        emoji = self.emojis.get(word)
        if emoji:
            return (emoji, "emoji")

        # Check color
        color = self.colors.get(word)
        if color:
            return (color, "color")

        # Check singular form for plurals
        if word.endswith('s') and len(word) > 2:
            singular = word[:-1]
            emoji = self.emojis.get(singular)
            if emoji:
                return (emoji, "emoji")
            color = self.colors.get(singular)
            if color:
                return (color, "color")

        return None

    def is_valid_word(self, word: str) -> bool:
        """Check if word is a valid emoji or color, including plural forms."""
        return self.get_word(word) is not None


# Global content manager instance
_content: Optional[ContentManager] = None


def get_content() -> ContentManager:
    """Get the global content manager"""
    global _content
    if _content is None:
        _content = ContentManager()
        _content.load_all()
    return _content
