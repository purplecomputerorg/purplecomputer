Status: Active. Step 1 is built (`purplecomputer/toy.py`, Play's code panel); steps 2 and 3 wait on how kids use it.

# Play's code panel builds a toy

Play is the one room without a code panel. Its panel could let a kid make a small toy: a key does something they wrote in Play. This uses Purple's own language, so it adds no second way of thinking about code (the reason Studio stopped offering blocks, and the reason PUR-159 parked Python on Purple).

## The idea in one line

A Play line runs now. The same line with a key in front runs when that key is pressed:

```
3 cats                      shows three cats now, as in Play
a: cow, say moo, drum cowbell
space: red, drum kick, blue, drum snare, purple, say purple!
```

## Fits the other code panels

Art, Music and Blocks open their panel on the code for what the kid just did by hand (`panels.Echo`), offer finished programs with Down (`panels.RECIPES`), and list the room's words in a side column (`panels.GUIDE`). Play's version:

- **Echo:** the last Play line with a key in front, e.g. `space: 3 cats`.
- **Recipes:** small finished toys (`a: cow, say moo` / `s: pig, say oink`; `any key: drum bongo, random emoji`; `1: 1 star, say 1`).
- **Guide:** Keys, Show, Say and sounds, More than one.
- **Above the code line:** the toy so far, one card per key showing its steps. Typing a key again replaces its card.
- **Trying it:** `play` turns the screen into the toy, Esc goes back. Rules never run while Play is the typing room, so typing never stops working.

## Words

| Word | Does | Reuses |
|---|---|---|
| `a:` `space:` `enter:` `1:` | runs the rest when that key is pressed | |
| no label | runs now | Play's evaluator |
| emoji, colors, math | shows it | Play's evaluator |
| `say ...` | speaks it; `say 2 + 3` says "five" | TTS, Play's math |
| `drum gong` | plays a drum | `roomkit` drum names |
| `,` | one step after another | code panel clause split |
| `any key:` | runs on every press, after the key's own rule | |
| `random animal` | a surprise from a category | |
| `fast` / `slow` | step speed in a sequence | Music's words |
| `tune asdf` | plays Music's keys | Music's runner |
| `start:` / `every 3:` | when the toy opens / a timer | |
| `save my farm` | keeps the toy in the Esc menu | |

## Forgiving like the rest of Purple

Nothing errors. A line shows what it became: a key card, or a result shown now.

- **The colon is optional** when the label can't mean anything else in Play: `s pig say oink`, `space cow`, `start say hi`, `every 3 random animal`, `any key drum`. `space`, `start` and `enter` are not emoji words.
- **`a`, `i` and digits need the colon**, since `a cow` and `1 star` already mean something in Play. Without it they run now, the kid sees no A card, and the guide's `a: cow` shows the fix.
- **`when`, `press` and `on` are allowed, never required:** `when a cow`, `press a cow`, `on 1: 1 star` all mean the key. `=` and `->` work like the colon; `-` doesn't, since `2 - 1` is Play's math.
- **Commas are optional too:** `say`, `drum`, `tune`, `random`, `fast` and `slow` start a new step, as Art's keywords do (`_COMMAND_STARTS` in `code_runner.py`). Same tradeoff as Art's `write`: `say I hit the drum` splits at `drum`.

These cases are pinned in `tests/test_toy.py`.

## Order

1. Key labels, no label, emoji/colors/math, `say`, `drum`, commas, the toy screen. All reuse.
2. `any key`, `random`, `fast`/`slow`, `tune`.
3. `start`, `every N`, `save`. `every` animates an idle screen (against the canvas rule), and `save` touches the room picker and saves: both need design first.

## Open questions

- Do kids want to make toys, or only play them? A small version on a few kids answers this before step 2.
- `any key` and a key's own rule: both run (as sketched) or the key wins?
- What `save` adds: the toy already lives in Play's code lines, so saves and Time Travel keep it; `save` would only be a name in the Esc menu.
