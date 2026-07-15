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
  - Instrument names: "akordion" -> "accordion", "marimab" -> "marimba"

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
  thing. A young child types a verb plus a bag of words and expects the
  computer to figure it out, regardless of order. "down blue 5",
  "down 5 blue", and "blue down 5" all mean the same thing to them.

  Mental model: bag-of-tokens with nearest-anchor assignment (see
  _classify_motion in code_runner.py). The line is tokenized into typed
  tokens (anchor / color / number / text). Every motion verb or direction
  word becomes an "anchor"; each number or color token is assigned to the
  nearest anchor by token index (ties favor the earlier anchor).
  Consecutive text tokens form one phrase bound to the previous anchor.
  The result is one motion plan per anchor, so a single line can carry
  several motions: "red down 5 blue right 5" paints red going down,
  then blue going right.

  Execution (_execute_motion_plans): plans run in order. Within a plan,
  color is applied before the move so the stroke paints in that color
  (brush color carries forward), then the turn, then the move, then any
  leftover text is written/painted in the verb's direction (this
  preserves "down hello" = write "hello" downward; "down 5 hello" moves
  down 5, then writes "hello").

  Why this is DRY: color handling previously lived in three places (a
  leading peel in _resolve, a trailing-color regex group copy-pasted into
  every motion handler, and a per-direction text handler). The tokenizer
  matches color in exactly one spot, reusing _resolve_leading_color
  (which already handles "dark blue"), and the six motion handlers
  collapsed into one data-driven executor.

Adding new commands
-------------------

  Art/Music: add a regex + handler to the _COMMANDS table, and add the
  keyword to _COMMAND_STARTS if it can appear mid-line.

  Play: add to the evaluation pipeline in SimpleEvaluator.evaluate().

  For fuzzy matching of new keywords, add them to the appropriate
  vocabulary list (_COMMAND_VOCAB, _KEYWORD_VOCAB, etc.).
