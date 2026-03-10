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

import inflect
from typeguard import suppress_type_checks

# Shared inflect engine for singular/plural conversion
_inflect_engine = inflect.engine()


def singularize(word: str) -> str | None:
    """Convert a plural word to singular using inflect.

    Returns the singular form as a plain str, or None if the word is not plural.
    Handles irregular plurals like tomatoes->tomato, cherries->cherry, wolves->wolf.
    """
    # inflect's type annotations expect its Word type but accept str at runtime.
    # Suppress typeguard's strict runtime checking for this call.
    with suppress_type_checks():
        result = _inflect_engine.singular_noun(word)
    if result:
        return str(result)
    return None


def pluralize(word: str) -> str:
    """Convert a singular word to plural using inflect.

    Handles irregular plurals like wolf->wolves, tomato->tomatoes, cherry->cherries.
    """
    with suppress_type_checks():
        result = _inflect_engine.plural(word)
    return str(result)


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
        # Unified prefix index: prefix -> [(word, color_hex|None, emoji|None), ...]
        # Ranked by kid-likelihood from rankings.txt
        self._word_prefix_index: dict[str, list[tuple[str, str | None, str | None]]] = {}

    def load_all(self) -> None:
        """Load content from all installed packs"""
        if self._loaded:
            return

        # Load built-in defaults (colors only, emoji come from packs)
        self._load_defaults()

        # Load from source-relative packs dir (works in dev and production)
        source_packs = Path(__file__).parent.parent / "packs"
        if source_packs.exists():
            for pack_dir in source_packs.iterdir():
                if pack_dir.is_dir():
                    self._load_pack(pack_dir)

        # Then load from user-installed packs (can override/extend)
        if self.packs_dir.exists():
            for pack_dir in self.packs_dir.iterdir():
                if pack_dir.is_dir():
                    self._load_pack(pack_dir)

        self._loaded = True
        self._build_prefix_indexes()

    def _load_defaults(self) -> None:
        """Load default colors. Emoji come from the core-emoji pack."""
        self.emojis = {}

        # Default colors for paint mixing (RYB primary/secondary + common colors)
        self.colors = {
            # Primary colors (paint)
            "red": "#ED1C24",      # Crayola red (classic fire-engine red)
            "yellow": "#FFEB00",   # Primary yellow
            "blue": "#1F75FE",     # Crayola blue (bright, clearly blue)

            # Secondary colors (what you get from mixing primaries)
            "orange": "#FF6600",   # Red + Yellow
            "green": "#48D370",    # What you get from mixing yellow + blue
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

            # More fun one-word colors
            "periwinkle": "#CCCCFF",
            "lilac": "#C8A2C8",
            "plum": "#8E4585",
            "orchid": "#DA70D6",
            "fuchsia": "#FF00FF",
            "mauve": "#E0B0FF",
            "ruby": "#E0115F",
            "emerald": "#50C878",
            "sapphire": "#0F52BA",
            "amber": "#FFBF00",
            "copper": "#B87333",
            "bronze": "#CD7F32",
            "ivory": "#FFFFF0",
            "aqua": "#00FFFF",
            "azure": "#007FFF",
            "cerulean": "#2A52BE",
            "cobalt": "#0047AB",
            "chartreuse": "#7FFF00",
            "khaki": "#C3B091",
            "burgundy": "#800020",
            "mulberry": "#C54B8C",
            "raspberry": "#E30B5C",
            "tangerine": "#FF9966",
            "apricot": "#FBCEB1",
            "lemon": "#FFF44F",
            "canary": "#FFEF00",
            "sunshine": "#FFFD37",
            "daffodil": "#FFFF31",
            "buttercup": "#F9E81E",
            "honey": "#EB9605",
            "mustard": "#FFDB58",
            "sepia": "#704214",
            "chocolate": "#7B3F00",
            "chestnut": "#954535",
            "cinnamon": "#D2691E",
            "ginger": "#B06500",
            "caramel": "#FFD59A",
            "rust": "#B7410E",
            "brick": "#CB4154",
            "bubblegum": "#FFC1CC",
            "blush": "#DE5D83",
            "hotpink": "#FF69B4",
            "carnation": "#FFA6C9",
            "spearmint": "#45B08C",
            "jade": "#00A86B",
            "moss": "#8A9A5B",
            "sage": "#9DC183",
            "pistachio": "#93C572",
            "cornflower": "#6495ED",
            "slate": "#708090",
            "eggplant": "#614051",
            "amethyst": "#9966CC",
            "iris": "#5A4FCF",
            "wisteria": "#C9A0DC",
            "heather": "#B7A2C7",
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
        """Load emoji pack: primary emoji and synonyms"""
        emoji_file = content_dir / "emoji.json"
        if emoji_file.exists():
            try:
                with open(emoji_file) as f:
                    data = json.load(f)
                    self.emojis.update(data)
            except (json.JSONDecodeError, OSError):
                pass

        # Load synonyms (alias -> primary word, resolved to emoji)
        synonyms_file = content_dir / "synonyms.json"
        if synonyms_file.exists():
            try:
                with open(synonyms_file) as f:
                    synonyms = json.load(f)
                    for alias, target in synonyms.items():
                        if target in self.emojis:
                            self.emojis[alias] = self.emojis[target]
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
        """Get emoji for a word, handling plurals (e.g., 'tomatoes' -> tomato emoji)."""
        word = word.lower().strip()
        # Try exact match first
        if emoji := self.emojis.get(word):
            return emoji
        # Try singular form (handles tomatoes->tomato, cherries->cherry, wolves->wolf, etc.)
        if (singular := singularize(word)) and (emoji := self.emojis.get(singular)):
            return emoji
        return None

    def emoji_to_word(self, emoji: str) -> Optional[str]:
        """Reverse lookup: get word for an emoji character"""
        for word, e in self.emojis.items():
            if e == emoji:
                return word
        return None

    def get_sound(self, sound_id: str) -> Optional[Path]:
        """Get path to a sound file"""
        return self.sounds.get(sound_id)

    def list_emojis(self) -> list[str]:
        """Get list of all available emoji words"""
        return sorted(self.emojis.keys())

    def _load_rankings(self) -> dict[str, int]:
        """Load word rankings from rankings.txt files in packs.

        Returns {word: rank} where lower rank = higher priority.
        """
        rankings: dict[str, int] = {}
        rank = 0
        # Check source-relative packs first, then user packs
        for packs_dir in [Path(__file__).parent.parent / "packs", self.packs_dir]:
            if not packs_dir.exists():
                continue
            for pack_dir in packs_dir.iterdir():
                rankings_file = pack_dir / "content" / "rankings.txt"
                if not rankings_file.exists():
                    continue
                try:
                    for line in rankings_file.read_text().splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            if line not in rankings:
                                rankings[line] = rank
                                rank += 1
                except OSError:
                    pass
        return rankings

    def _build_prefix_indexes(self) -> None:
        """Build unified prefix index for instant autocomplete.

        Called once at load time. Merges emojis and colors into a single index,
        ranked by kid-likelihood from rankings.txt.
        """
        rankings = self._load_rankings()
        unranked = len(rankings)

        # prefix -> {word: (color_hex|None, emoji|None)}
        by_prefix: dict[str, dict[str, tuple[str | None, str | None]]] = {}

        def _add_word(word: str, color: str | None, emoji: str | None) -> None:
            plural = pluralize(word)
            for form in [word, plural]:
                for i in range(2, len(form) + 1):
                    p = form[:i]
                    bucket = by_prefix.setdefault(p, {})
                    if form in bucket:
                        # Merge: word can be both a color and an emoji
                        old_color, old_emoji = bucket[form]
                        bucket[form] = (color or old_color, emoji or old_emoji)
                    else:
                        bucket[form] = (color, emoji)

        for word, emoji in self.emojis.items():
            _add_word(word, None, emoji)

        for name, hex_code in self.colors.items():
            _add_word(name, hex_code, None)

        # Sort by rank, then dedup: keep the best-ranked word for each emoji/color
        def _dedup(entries: list[tuple[str, str | None, str | None]]):
            seen_emojis: set[str] = set()
            seen_colors: set[str] = set()
            result = []
            for w, c, e in entries:
                if e and e in seen_emojis:
                    continue
                if c and not e and c in seen_colors:
                    continue
                if e:
                    seen_emojis.add(e)
                if c:
                    seen_colors.add(c)
                result.append((w, c, e))
            return result

        self._word_prefix_index = {
            p: _dedup(sorted(
                [(w, c, e) for w, (c, e) in entries.items()],
                key=lambda x: rankings.get(x[0], unranked),
            ))
            for p, entries in by_prefix.items()
        }

    def search_words(self, prefix: str) -> list[tuple[str, str | None, str | None]]:
        """Search for words starting with prefix, returns [(word, color_hex|None, emoji|None), ...].

        Unified ranked search across emojis and colors.
        """
        return self._word_prefix_index.get(prefix.lower(), [])

    def search_emojis(self, prefix: str) -> list[tuple[str, str]]:
        """Search for emojis starting with prefix, returns [(word, emoji), ...]."""
        return [
            (w, e) for w, _c, e in self.search_words(prefix) if e is not None
        ]

    def get_color(self, word: str) -> Optional[str]:
        """Get hex color code for a color name, handling plurals (e.g., 'reds' -> red)."""
        word = word.lower().strip()
        # Try exact match first
        if color := self.colors.get(word):
            return color
        # Try singular form
        if (singular := singularize(word)) and (color := self.colors.get(singular)):
            return color
        return None

    def get_modified_color(self, text: str) -> tuple[str, str, list[str], str] | None:
        """Parse adjective(s) + color name, e.g. 'bright green', 'dark light blue'.

        Returns (modified_hex, base_hex, adjectives, color_name) or None.
        Adjectives are applied left to right.
        """
        from .color_mixing import COLOR_ADJECTIVES, modify_color

        words = text.lower().strip().split()
        if len(words) < 2:
            return None

        # Collect leading adjectives, rest is the color name
        adjectives = []
        for i, w in enumerate(words):
            if w in COLOR_ADJECTIVES:
                adjectives.append(w)
            else:
                break
        else:
            return None  # All words were adjectives, no color

        if not adjectives:
            return None

        color_name = " ".join(words[len(adjectives):])
        base_hex = self.get_color(color_name)
        if not base_hex:
            return None

        # Apply adjectives left to right
        modified = base_hex
        for adj in adjectives:
            modified = modify_color(modified, adj)

        return (modified, base_hex, adjectives, color_name)

    def search_colors(self, prefix: str) -> list[tuple[str, str]]:
        """Search for colors starting with prefix, returns [(name, hex), ...]."""
        return [
            (w, c) for w, c, _e in self.search_words(prefix) if c is not None
        ]

    def list_colors(self) -> list[str]:
        """Get list of all available color names"""
        return sorted(self.colors.keys())

    def get_word(self, word: str) -> tuple[str, str] | None:
        """Get emoji or color for a word, including plural forms.

        Returns (value, type) where type is 'emoji' or 'color', or None if not found.
        For plurals like 'tomatoes', 'cherries', 'wolves', returns the emoji/color.
        """
        word = word.lower().strip()

        # Check emoji first (get_emoji handles plurals via singularize)
        emoji = self.get_emoji(word)
        if emoji:
            return (emoji, "emoji")

        # Check color (get_color handles plurals via singularize)
        color = self.get_color(word)
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
