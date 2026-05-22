Smart Command Resolution
========================

Design document for Purple Computer's typo tolerance and fuzzy matching
system across all rooms (Play, Art, Music).

Design principle: always do the best-guess reasonable thing.

Architecture: Two Layers
------------------------

Layer 1: Content-level fuzzy (universal, DRY)

  get_emoji() and get_color() in content.py have a fuzzy fallback using
  Damerau-Levenshtein distance. This propagates to ALL rooms automatically.

  Thresholds (conservative to avoid false positives):
  - Min 5 chars (with 400+ emojis, any 3-4 char word collides)
  - Max DL distance 1 (single typo: insertion, deletion, substitution,
    or transposition)
  - "dinno" -> "dino", "purpel" -> "purple", "oragne" -> "orange"
  - "barn" does NOT match "bear" (4 chars, below minimum)

Layer 2: Per-room structural fuzzy (for keywords, operators)

  Each room has structural keywords not in the content system. These use
  fuzzy_match_small() (difflib, min 3 chars) on small curated vocabularies
  where false positives are unlikely.

  Play room:
  - Speech prefixes: "sya" -> "say", "talkk" -> "talk"
  - Operator words: "timess" -> "times" (only between digits)
  - Repeat/end: "repet" -> "repeat", "ened" -> "end"

  Art room:
  - Command keywords: "forwrd" -> "forward", "trun" -> "turn"
  - Turn/face arguments: "rite" -> "right", "dwon" -> "down"
  - Color arguments: "bleu" -> "blue" (via content layer + resolution)

  Music room:
  - Command keywords: "chooze" -> "choose", "lettrs" -> "letters"
  - Instrument names: "xylaphone" -> "xylophone", "marimab" -> "marimba"

Shared module: purple_tui/fuzzy.py
-----------------------------------

  damerau_levenshtein(s1, s2)
    Standard DL distance. Counts transpositions as 1 edit.

  fuzzy_match(word, vocabulary, min_len=5)
    Content-level: DL distance, conservative. For large vocabularies
    (emojis, colors) where false positives are dangerous.

  fuzzy_match_small(word, vocabulary, cutoff=0.6)
    Command-level: difflib, flexible. For small curated vocabularies
    (10-20 words) where false positives are unlikely.

Correction tracking
-------------------

  Content layer: content._last_correction = (original, corrected)
  Art/Music runners: runner.corrections = [(original, corrected), ...]

  Corrections flow to RecallHint in the REPL panel, showing
  "forwrd -> forward" once, then storing the corrected command
  for Enter-to-recall.

Edge cases
----------

  Short words (3-4 chars): NOT fuzzy matched at content layer.
  "barn", "fog", "big" all stay as-is. This is correct: with 400+
  emojis, almost any short word collides with something.

  Operator words: only fuzzy matched when between digits.
  "3 timess 2" corrects. "cat timess 3" also corrects (the word
  is between operands). "plum" does NOT become "plus".

  "hello" vs "yellow": DL distance is 3, so content layer won't
  match. Art room's difflib-based resolution was replaced with
  fuzzy_match_small which also won't match at min 3 chars (hello
  is not in the command vocabulary).

Argument ordering (free-order motion args)
------------------------------------------

  Design principle (same as above): always do the best-guess reasonable
  thing. A 4-7 year old types a verb plus a bag of words and expects the
  computer to figure it out, regardless of order. "down blue 5",
  "down 5 blue", and "blue down 5" all mean the same thing to them.

  Mental model: a line is split into command chunks at command-keyword
  boundaries (see _split_commands), so each chunk has exactly one motion
  verb. Within a chunk, the remaining tokens are an unordered bag of:
    - a distance (any bare-number token)
    - a color (a color word, optionally preceded by adjectives like
      "dark"/"light"; may appear anywhere, not just first or last)
    - leftover text (anything else)

  Resolution order inside a chunk:
    1. Apply the color if one is present (reusing _resolve_leading_color,
       which already handles "dark blue").
    2. Move the distance if one is present.
    3. If leftover non-color text remains, write/paint it in the verb's
       direction (this preserves "down hello" = write "hello" downward).
       "down 5 hello" therefore moves down 5, then writes "hello".

  Why this is DRY: color handling previously lived in three places (a
  leading peel in _resolve, a trailing-color regex group copy-pasted into
  every motion handler, and _do_direction_text). Free-order parsing folds
  all three into one shared _parse_motion_args helper, so color is matched
  in exactly one spot and the combinatorial motion regex table collapses
  to one "verb + rest" pattern per family.

  Cross-chunk ordering (e.g. "blue down 5", where the color is its own
  leading chunk) is handled separately by the leading-color peel in
  _resolve, which applies the color and re-dispatches the remainder.

Adding new commands
-------------------

  Art/Music: add a regex + handler to the _COMMANDS table, and add the
  keyword to _COMMAND_STARTS if it can appear mid-line.

  Play: add to the evaluation pipeline in SimpleEvaluator.evaluate().

  For fuzzy matching of new keywords, add them to the appropriate
  vocabulary list (_COMMAND_VOCAB, _KEYWORD_VOCAB, etc.).
